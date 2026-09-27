"""LLM receipt extraction over an OpenAI-compatible chat completions endpoint.

The request follows the configuration proven in the MVP-R0 spike (docs/vLLM_MANUAL_TEST.md):
compact output keys, a strict ``json_schema`` response format, ``max_tokens`` sized for a long
receipt, and ``chat_template_kwargs.reasoning_strength`` for reasoning models such as
``muse-glimmer``. The same instructions serve text (OCR or PDF) and image input.

Receipts come from any shop, country and language, so the rules are general and the Finnish
strings in them are labelled examples (Q27). On the text path the receipt lines are numbered
and the model accounts for every one: a product cites its lines in ``l``, every other line is
listed in ``x`` with its kind. Reconciliation (``receipt_processing``) uses that to find the
lines the model left out, without knowing anything about the receipt's format.
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
from app.parsers.base import (
    OTHER_LINE_KINDS,
    ExtractedLine,
    ExtractionMethod,
    OtherLine,
    ReceiptExtraction,
)
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

# The raw completion is stored on the receipt for diagnosis; a runaway answer is capped
RAW_COMPLETION_LIMIT = 64 * 1024

# What the model answers for c when a line is not food at all. Deliberately not a category:
# a category would be a legal pick on the review screen and would put towels into stock (Q1).
NON_FOOD = "household"

# The catalog is a naming aid only. Worded "When an equivalent product is listed here, use
# its name exactly", a warm catalog read as the list of what to extract: the model returned
# the 6 listed products of a 15-line receipt and dropped the rest (Q27). H17 measured the
# block's category benefit, so it stays, reworded; scripts/measure_extraction.py compares.
CATALOG_BLOCK = (
    "\n- Extract every product line on the receipt, whether or not it is in this list."
    " The list only tells you which name to use for an equivalent product: when one is"
    " listed here, use its name exactly for g. Known products: {names}."
)

_INSTRUCTIONS = """Extract every purchased product from this receipt. It may come from any shop, country and language.

Rules:
- The receipt lines are numbered ("12: ..."). Account for every numbered line: each one is
  either part of a product in p or listed in x. On an image there are no numbers: answer
  l = [] and x = [].
- One entry per product. n = the product name exactly as written, without the price.
- l = the numbers of all the lines the product was read from: its name line, or both lines
  when a long name wraps, and any line that gives its count, weight or unit price, whether
  that line comes before or after the name.
- p = the line total charged for the product, as a number, never the unit price; null if
  none is printed.
- g = the simple generic English name a home cook would write on a shopping list. No brand,
  size, fat content or percentage, or flavour-neutral variant, and the same name for equivalent
  cuts. Examples: SNELLMAN NAUDAN JAUHELIHA 10% -> "Ground beef"; ATRIA KANAN FILEESUIKALE ->
  "Chicken fillet"; VALIO KEVYTMAITOJUOMA 1L -> "Milk".
- Always write g in the singular, whatever the amount: "Apple", "Carrot", "Banana", never
  "Apples" or "Carrots". One product is one name.
- Household and cleaning products get an everyday English name too: SIENILIINA ->
  "Cleaning cloth"; PYYKKIETIKKA -> "Laundry vinegar". Answer household for their c - they are
  not food and do not go in the fridge. Food keeps its category as below.{known_products}
- A line next to a product that gives a count and a unit price means q = that count.
  Examples: "3 KPL 1,88 €/KPL" below the name; "2 x 1,49" above the name.
- A line next to a product that gives a weight and a price per kg or lb means w = that
  weight in kg. Example: "0,386 KG 3,89 €/KG" -> w = 0.386.
- Otherwise q = 1 and w = null.
- c = the best category id for the product, or null if none fits (for example household or
  cleaning products). Categories: {categories}.
- pw = what one piece of this roughly weighs in grams, when it is something a cook counts one
  at a time but the shop may sell by weight. Examples: apple -> 125; banana -> 120; onion ->
  110; tomato -> 100. Use null when counting pieces makes no sense: milk, mince, flour,
  washing-up liquid.
- sl = how many days this keeps unopened in its normal place, as a round estimate. Examples:
  banana -> 7; carrot -> 21; milk -> 10; hard cheese -> 30; dried pasta -> 720. Estimate it
  for every food line, not only these; use null if you truly cannot say.
- os = how many days it keeps after the pack is opened. Examples: milk -> 5; yoghurt -> 5;
  juice -> 5; hard cheese -> 14; ketchup -> 180. Use null for loose fruit and vegetables and
  anything else that is not opened.
- s = the store chain or store name from the header; d = the purchase date as YYYY-MM-DD.
  Use null when absent.
- lc = the receipt's language as an ISO 639-1 code; cc = the shop's country as an ISO 3166-1
  alpha-2 code. Use null when unsure.
- The store header, totals, subtotals, tax lines, payment, discounts, deposits and fees are
  not products. List each such numbered line in x as {{"l": line number, "k": kind, "a":
  amount}}, where k is one of header, total, subtotal, tax, payment, discount, deposit, fee,
  other, and a is the amount printed on it as a signed number (negative for a discount), or
  null. Examples: UKUPNO, SUMME and TOTAL are totals; PDV and MwSt are tax; POPUST and
  Rabatt are discounts; Pfand is a deposit.
- t = the receipt's grand total as a number, or null if none is printed.
- Examples of Finnish words often misread: TUMMA RYPÄLE -> "Grape" (RUSINA is "Raisin");
  TIKKUPERUNAT -> "French fries"; TÄYSMEHU OMENA -> "Apple juice" (MEHU is juice);
  RIISIPIIRAKKA -> "Karelian pasty"; MONIVITAMIINI APPELSIINI -> "Multivitamin juice", but
  MONIVITAMIINI with no flavour is a vitamin supplement, household; VALMISRUOKA, ATERIA ->
  c = ready_meals.

Return only compact JSON: {{"s": chain, "d": date, "lc": language, "cc": country, "t": total, "p": [{{"n": name, "l": [line numbers], "p": line total or null, "g": generic name, "q": quantity, "w": weight_kg or null, "c": category or null, "pw": grams per piece or null, "sl": shelf life days or null, "os": opened shelf life days or null}}], "x": [{{"l": line number, "k": kind, "a": amount or null}}]}}."""

_RETRY = """These numbered receipt lines were not accounted for in a first reading. Extract any
products among them with the same rules, citing the same line numbers in l, and list every
other one of these lines in x."""


def number_receipt_lines(text: str) -> list[tuple[int | None, str]]:
    """Every non-blank line of the receipt with its number in the prompt.

    Lines that can never be products (totals, VAT, payment, discounts, fees) are left out of
    the prompt and get None; the rest are numbered from 1 in receipt order. The prompt shows
    the numbers, and the model cites them (Q27).
    """
    numbered: list[tuple[int | None, str]] = []
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if is_skip_line(line):
            numbered.append((None, line))
            continue
        count += 1
        numbered.append((count, line))
    return numbered


def prompt_lines(text: str) -> list[str]:
    """The lines the prompt numbers; line ``n`` is ``prompt_lines(text)[n - 1]``."""
    return [line for number, line in number_receipt_lines(text) if number is not None]


def prefilter_receipt_text(text: str) -> str:
    """Drop lines that can never be products, keeping the header, product and quantity lines.

    Shrinks the prompt and removes totals and VAT numbers the model might mistake for items.
    """
    return "\n".join(prompt_lines(text))


def format_numbered(lines: Sequence[tuple[int, str]]) -> str:
    return "\n".join(f"{number}: {line}" for number, line in lines)


def build_instructions(
    categories: Sequence[CategoryOption], known_products: Sequence[str] = ()
) -> str:
    """The extraction prompt.

    The catalog block is on by default (`EXTRACTION_OFFERS_CATALOG`). It keeps generic
    names consistent between receipts, capped at 300 names and growing with the catalog.
    A name is a key now (H11) and confirm learns the generic name as a synonym, so the
    block was expected to be droppable, but H17 measured the categories the model fills
    in falling from 40 to 30-31 of 49 without it, so it stays; the setting turns it off.
    It says outright that it is a naming aid, not the list of what to read (Q27).
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
    # The block used to end "and set pw, sl and os to null for it - the system already
    # knows those". It was meant to save the model work on products the catalog knows,
    # and instead it silenced the estimates for the whole receipt: measured on the
    # 49-line fixture, shelf lives fell from 39 of 49 to 1 of 49 as soon as any catalog
    # was offered (Q7). Every product created from a receipt read with a warm catalog
    # therefore fell back to its category's blanket shelf life, which is what Q6 exists
    # to avoid. Estimating for a known product costs a few tokens and is discarded by
    # `_fill_gaps` anyway; not estimating costs the catalog its accuracy.
    known = CATALOG_BLOCK.format(names=", ".join(unique)) if unique else ""
    return _INSTRUCTIONS.format(categories=listed, known_products=known)


def _generic_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    tidy = " ".join(value.split())
    return tidy[:1].upper() + tidy[1:] if tidy else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _positive(value: Any) -> float | None:
    """A rough estimate is welcome; zero, negative and nonsense are not (Q2, Q6)."""
    number = _number(value)
    return number if number is not None and number > 0 else None


def _positive_int(value: Any) -> int | None:
    number = _positive(value)
    return round(number) if number is not None else None


def _line_number(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if value >= 1 and value == int(value) else None


def _line_numbers(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    numbers = (_line_number(item) for item in value)
    return sorted({number for number in numbers if number is not None})


def _code(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    tidy = value.strip()
    return tidy if tidy.isalpha() and len(tidy) == 2 else None


def build_response_schema(category_ids: Sequence[str]) -> dict[str, Any]:
    """Strict JSON schema for the compact contract; ``c`` may only be a known id or null."""
    return {
        "type": "object",
        "properties": {
            "s": {"type": ["string", "null"]},
            "d": {"type": ["string", "null"]},
            "lc": {"type": ["string", "null"]},
            "cc": {"type": ["string", "null"]},
            "t": {"type": ["number", "null"]},
            "p": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "string"},
                        "l": {"type": "array", "items": {"type": "integer"}},
                        "p": {"type": ["number", "null"]},
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
                    "required": ["n", "l", "p", "g", "q", "w", "c", "pw", "sl", "os"],
                },
            },
            "x": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "l": {"type": "integer"},
                        "k": {"enum": list(OTHER_LINE_KINDS)},
                        "a": {"type": ["number", "null"]},
                    },
                    "required": ["l", "k", "a"],
                },
            },
        },
        "required": ["s", "d", "lc", "cc", "t", "p", "x"],
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


def _other_lines(value: Any) -> list[OtherLine]:
    """The non-product lines the model listed; an entry without a line number is useless."""
    if not isinstance(value, list):
        return []
    others: list[OtherLine] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        number = _line_number(entry.get("l"))
        if number is None:
            continue
        kind = str(entry.get("k") or "").strip().casefold()
        others.append(
            OtherLine(
                line=number,
                kind=kind if kind in OTHER_LINE_KINDS else "other",  # type: ignore[arg-type]
                amount=_number(entry.get("a")),
            )
        )
    return others


def parse_completion(
    content: str, category_ids: set[str], method: ExtractionMethod
) -> ReceiptExtraction:
    """Map the model's compact JSON to a ``ReceiptExtraction``.

    Tolerant where a wrong value should not fail a receipt (unknown category, bad date, a
    price left in a name) and strict where the output is unusable (no product list). A
    product entry that cannot be used is counted in ``invalid_entries``, never dropped
    without a trace (Q27).
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
    invalid = 0
    for entry in products:
        if not isinstance(entry, dict):
            invalid += 1
            continue
        name = _TRAILING_PRICE.sub("", str(entry.get("n") or "")).strip()
        if not name:
            invalid += 1
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
                    source_lines=_line_numbers(entry.get("l")),
                    price=_number(entry.get("p")),
                )
            )
        except ValidationError as exc:
            invalid += 1
            logger.warning(
                "Skipping invalid extracted line", extra={"errors": exc.errors()}
            )
    if invalid:
        logger.warning(
            "Model returned unusable product entries",
            extra={"invalid_entries": invalid, "method": method},
        )

    store = data.get("s")
    return ReceiptExtraction(
        method=method,
        store_chain=store.strip() if isinstance(store, str) and store.strip() else None,
        purchase_date=_parse_date(data.get("d")),
        lines=lines,
        other_lines=_other_lines(data.get("x")),
        receipt_total=_number(data.get("t")),
        language=_code(data.get("lc")),
        country=_code(data.get("cc")),
        invalid_entries=invalid,
    )


def _cap(content: str) -> str:
    """At most RAW_COMPLETION_LIMIT bytes of UTF-8, cut on a character boundary."""
    encoded = content.encode("utf-8")
    if len(encoded) <= RAW_COMPLETION_LIMIT:
        return content
    return encoded[:RAW_COMPLETION_LIMIT].decode("utf-8", errors="ignore")


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
        choice = body["choices"][0]
        message_content = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMExtractionError("LLM response has no message content") from exc
    logger.debug("LLM raw completion", extra={"chars": len(message_content)})
    # A cut-off answer can still parse as a shorter list; that is how lines vanish (Q27)
    if isinstance(choice, dict) and choice.get("finish_reason") == "length":
        raise LLMExtractionError(
            f"LLM response was truncated at max_tokens ({settings.LLM_MAX_TOKENS})"
        )

    result = parse_completion(message_content, set(category_ids), method)
    result.raw_completion = _cap(message_content)
    logger.info(
        "Receipt extracted",
        extra={
            "model": settings.LLM_MODEL,
            "method": method,
            "lines": len(result.lines),
            "other_lines": len(result.other_lines),
            "invalid_entries": result.invalid_entries,
            "seconds": round(time.monotonic() - started, 1),
        },
    )
    return result


async def extract_from_text(
    text: str,
    categories: Sequence[CategoryOption],
    known_products: Sequence[str] = (),
) -> ReceiptExtraction:
    """Extract products from OCR or PDF text, every prompt line numbered."""
    instructions = build_instructions(categories, known_products)
    numbered = [(n, line) for n, line in number_receipt_lines(text) if n is not None]
    prompt = f"{instructions}\n\nReceipt:\n{format_numbered(numbered)}"
    return await _complete(prompt, categories, method="text")


async def extract_unaccounted_lines(
    lines: Sequence[tuple[int, str]], categories: Sequence[CategoryOption]
) -> ReceiptExtraction:
    """One targeted read of the lines a first read did not account for (Q27).

    Same rules, schema and categories, but no catalog block: the block is what a first
    read tends to mistake for the list of products to extract.
    """
    instructions = build_instructions(categories, ())
    prompt = f"{instructions}\n\n{_RETRY}\n\nReceipt lines:\n{format_numbered(lines)}"
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
