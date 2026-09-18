"""LLM receipt extraction over an OpenAI-compatible chat completions endpoint.

The request follows the configuration proven in the MVP-R0 spike (docs/vLLM_MANUAL_TEST.md):
compact output keys, a strict ``json_schema`` response format, ``max_tokens`` sized for a long
receipt, and ``chat_template_kwargs.reasoning_strength`` for reasoning models such as
``muse-glimmer``. The same instructions serve text (OCR or PDF) and image input.
"""

import base64
import json
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.parsers.base import ExtractedLine, ExtractionMethod, ReceiptExtraction
from app.parsers.receipt_lines import is_skip_line

logger = get_logger(__name__)


class LLMExtractionError(Exception):
    """The LLM call failed or returned output that does not match the contract."""


@dataclass(frozen=True)
class CategoryOption:
    """A category the model may assign: the id it must return and a human-readable name."""

    id: str
    name: str


# Lines that are never products: separators, totals, payment, VAT table, discounts, fees.
_TRAILING_PRICE = re.compile(r"\s+-?\d+[,.]\d{2}(\s*€)?$")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

# Catalog names offered to the model so equivalent products keep one name; bounds the prompt
MAX_KNOWN_PRODUCTS = 300

# What the model answers for c when a line is not food at all. Deliberately not a category:
# a category would be a legal pick on the review screen and would put towels into stock (Q1).
NON_FOOD = "household"

_INSTRUCTIONS = """Extract every purchased product from this grocery receipt.

Rules:
- One entry per product line. n = the product name exactly as written, without the price.
- g = the simple generic English name a home cook would write on a shopping list. No brand,
  size, fat content or percentage, or flavour-neutral variant, and the same name for equivalent
  cuts. Examples: SNELLMAN NAUDAN JAUHELIHA 10% -> "Ground beef"; ATRIA KANAN FILEESUIKALE ->
  "Chicken fillet"; VALIO KEVYTMAITOJUOMA 1L -> "Milk".
- Always write g in the singular, whatever the amount: "Apple", "Carrot", "Banana", never
  "Apples" or "Carrots". One product is one name.
- Household and cleaning products get an everyday English name too: SIENILIINA ->
  "Cleaning cloth"; PYYKKIETIKKA -> "Laundry vinegar". Answer household for their c - they are
  not food and do not go in the fridge. Food keeps its category as below.{known_products}
- A following line like "3 KPL 1,88 €/KPL" means q = 3 for the product above it.
- A following line like "0,386 KG 3,89 €/KG" means w = 0.386 (kg) for the product above it.
- Otherwise q = 1 and w = null.
- c = the best category id for the product, or null if none fits (for example household or
  cleaning products). Categories: {categories}.
- pw = what one piece of this roughly weighs in grams, when it is something a cook counts one
  at a time but the shop may sell by weight. Examples: apple -> 125; banana -> 120; onion ->
  110; tomato -> 100. Use null when counting pieces makes no sense: milk, mince, flour,
  washing-up liquid.
- sl = how many days this keeps unopened in its normal place, as a round estimate. Examples:
  banana -> 7; carrot -> 21; milk -> 10; hard cheese -> 30; dried pasta -> 720. Use null if
  you truly cannot say.
- os = how many days it keeps after the pack is opened. Examples: milk -> 5; yoghurt -> 5;
  juice -> 5; hard cheese -> 14; ketchup -> 180. Use null for loose fruit and vegetables and
  anything else that is not opened.
- s = the store chain or store name from the header; d = the purchase date as YYYY-MM-DD.
  Use null when absent.
- Skip store header, totals, discounts (NORM., ALENNUS), fees, deposits, payment and VAT
  lines as products.

Return only compact JSON: {{"s": chain, "d": date, "p": [{{"n": name, "g": generic name, "q": quantity, "w": weight_kg or null, "c": category or null, "pw": grams per piece or null, "sl": shelf life days or null, "os": opened shelf life days or null}}]}}."""


def prefilter_receipt_text(text: str) -> str:
    """Drop lines that can never be products, keeping the header, product and quantity lines.

    Shrinks the prompt and removes totals and VAT numbers the model might mistake for items.
    """
    return "\n".join(
        line for line in text.splitlines() if line.strip() and not is_skip_line(line)
    )


def build_instructions(
    categories: Sequence[CategoryOption], known_products: Sequence[str] = ()
) -> str:
    """The extraction prompt.

    The catalog block is off by default since H17. It was there to keep generic names
    consistent between receipts, capped at 300 names and growing with the catalog. A
    name is a key now (H11), and confirm learns the generic name as a synonym, so
    "Minced beef" reaches "Ground beef" next week without the prompt carrying the
    catalog at all. `EXTRACTION_OFFERS_CATALOG` puts the list back.
    """
    listed = ", ".join(f"{c.id} ({c.name})" for c in categories) or "none"
    if not settings.EXTRACTION_OFFERS_CATALOG:
        known_products = ()
    first_spelling: dict[str, str] = {}
    for name in known_products:
        tidy = " ".join(name.split())
        if tidy:
            first_spelling.setdefault(tidy.casefold(), tidy)
    unique = sorted(first_spelling.values(), key=str.casefold)[:MAX_KNOWN_PRODUCTS]
    known = (
        "\n  When an equivalent product is listed here, use its name exactly, and set "
        "pw, sl and os to null for it - the system already knows those. "
        f"Known products: {', '.join(unique)}."
        if unique
        else ""
    )
    return _INSTRUCTIONS.format(categories=listed, known_products=known)


def _generic_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    tidy = " ".join(value.split())
    return tidy[:1].upper() + tidy[1:] if tidy else None


def _positive(value: Any) -> float | None:
    """A rough estimate is welcome; zero, negative and nonsense are not (Q2, Q6)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _positive_int(value: Any) -> int | None:
    number = _positive(value)
    return round(number) if number is not None else None


def build_response_schema(category_ids: Sequence[str]) -> dict[str, Any]:
    """Strict JSON schema for the compact contract; ``c`` may only be a known id or null."""
    return {
        "type": "object",
        "properties": {
            "s": {"type": ["string", "null"]},
            "d": {"type": ["string", "null"]},
            "p": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "string"},
                        "g": {"type": "string"},
                        "q": {"type": "number"},
                        "w": {"type": ["number", "null"]},
                        # "household" is a sentinel, not a category: it marks a line as
                        # not food rather than filing it anywhere (Q1)
                        "c": {"enum": [*category_ids, NON_FOOD, None]},
                        "pw": {"type": ["number", "null"]},
                        "sl": {"type": ["integer", "null"]},
                        "os": {"type": ["integer", "null"]},
                    },
                    "required": ["n", "g", "q", "w", "c", "pw", "sl", "os"],
                },
            },
        },
        "required": ["s", "d", "p"],
    }


def extract_json_object(content: str) -> dict[str, Any]:
    """The JSON object in a completion, past any reasoning block or code fence.

    Shared with product_selection: muse-glimmer is a reasoning model and wraps
    its answer, so both callers need the same unwrapping."""
    content = _THINK.sub("", content).strip()
    fence = _FENCE.search(content)
    if fence:
        content = fence.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end < start:
        raise LLMExtractionError("LLM response contains no JSON object")
    try:
        data = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMExtractionError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMExtractionError("LLM response JSON is not an object")
    return data


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_completion(
    content: str, category_ids: set[str], method: ExtractionMethod
) -> ReceiptExtraction:
    """Map the model's compact JSON to a ``ReceiptExtraction``.

    Tolerant where a wrong value should not fail a receipt (unknown category, bad date, a
    price left in a name) and strict where the output is unusable (no product list).
    """
    data = extract_json_object(content)
    products = data.get("p")
    if not isinstance(products, list):
        raise LLMExtractionError("LLM response has no product list")

    # The strict json_schema pins ``c`` to the known ids, but the gateway does not always
    # enforce it: muse-glimmer answers "Dairy" for the id `dairy`, and a case-sensitive
    # comparison then silently nulls every category, which leaves confirm unable to create
    # any product. Match on case, not on luck.
    by_fold = {str(known).casefold(): known for known in category_ids}

    lines: list[ExtractedLine] = []
    for entry in products:
        if not isinstance(entry, dict):
            continue
        name = _TRAILING_PRICE.sub("", str(entry.get("n") or "")).strip()
        if not name:
            continue
        raw_category = entry.get("c")
        folded = str(raw_category).casefold() if isinstance(raw_category, str) else ""
        non_food = folded == NON_FOOD
        category = None if non_food else by_fold.get(folded)
        quantity = entry.get("q")
        try:
            lines.append(
                ExtractedLine(
                    name=name,
                    generic_name=_generic_name(entry.get("g")),
                    quantity=1.0 if quantity is None else quantity,
                    weight_kg=entry.get("w"),
                    category=category,
                    piece_grams=_positive(entry.get("pw")),
                    shelf_life_days=_positive_int(entry.get("sl")),
                    opened_shelf_life_days=_positive_int(entry.get("os")),
                    non_food=non_food,
                )
            )
        except ValidationError as exc:
            logger.warning(
                "Skipping invalid extracted line", extra={"errors": exc.errors()}
            )

    store = data.get("s")
    return ReceiptExtraction(
        method=method,
        store_chain=store.strip() if isinstance(store, str) and store.strip() else None,
        purchase_date=_parse_date(data.get("d")),
        lines=lines,
    )


async def _complete(
    content: str | list[dict[str, Any]],
    categories: Sequence[CategoryOption],
    method: ExtractionMethod,
) -> ReceiptExtraction:
    category_ids = [c.id for c in categories]
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "receipt",
                "schema": build_response_schema(category_ids),
                "strict": True,
            },
        },
    }
    if settings.LLM_REASONING_STRENGTH:
        payload["chat_template_kwargs"] = {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            response = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise LLMExtractionError(f"LLM request failed: {exc!r}") from exc

    try:
        message_content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMExtractionError("LLM response has no message content") from exc
    logger.debug("LLM raw completion", extra={"chars": len(message_content)})

    result = parse_completion(message_content, set(category_ids), method)
    logger.info(
        "Receipt extracted",
        extra={
            "model": settings.LLM_MODEL,
            "method": method,
            "lines": len(result.lines),
            "seconds": round(time.monotonic() - started, 1),
        },
    )
    return result


async def extract_from_text(
    text: str,
    categories: Sequence[CategoryOption],
    known_products: Sequence[str] = (),
) -> ReceiptExtraction:
    """Extract products from OCR or PDF text."""
    instructions = build_instructions(categories, known_products)
    prompt = f"{instructions}\n\nReceipt:\n{prefilter_receipt_text(text)}"
    return await _complete(prompt, categories, method="text")


async def extract_from_image(
    image: bytes,
    content_type: str,
    categories: Sequence[CategoryOption],
    known_products: Sequence[str] = (),
) -> ReceiptExtraction:
    """Extract products by reading the receipt image with a vision-capable model."""
    data_url = f"data:{content_type};base64,{base64.b64encode(image).decode()}"
    content: list[dict[str, Any]] = [
        {"type": "text", "text": build_instructions(categories, known_products)},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    return await _complete(content, categories, method="vision")
