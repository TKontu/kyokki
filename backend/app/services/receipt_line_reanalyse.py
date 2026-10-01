"""Re-ask the model for one receipt line, with an optional hint from the cook (Q38).

The review screen can already re-read a whole receipt, or let the cook fix a line by hand.
Neither helps when the model named a line wrong and the fix is "ask again, better": one
small request for that line alone, its generic name and category only - never the catalog,
which is exactly how a wrong name got copied onto a different product in the first place
(Q37). The cook's hint, when given, outranks the printed text: it is their word for what the
line actually is.

Nothing here teaches an alias, a synonym or a product. The line's new generic name, category
and resolution are written back into `receipt.ocr_structured` alone; only confirm (unchanged
by this module) turns a line into a learned key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.logging import get_logger
from app.crud.category import get_categories
from app.models.receipt import Receipt
from app.schemas.receipt import ExtractedItem, ReceiptStatus, items_from_structured
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.llm_extractor import CategoryOption, extract_json_object
from app.services.llm_http import LLMAuthError, post_chat
from app.services.non_food import known_non_food
from app.services.product_resolution import ProductResolution, ResolvableLine
from app.services.receipt_confirm import UNKNOWN_CHAIN
from app.services.store_chain import normalize_store_chain

logger = get_logger(__name__)

# A longer hint is more likely pasted junk than a real answer (also enforced by the
# schema's own constant; kept here too so this module has no silent dependency on it).
HINT_MAX_LENGTH = 200

# What the model answers for `c` when a line is not food at all. A copy of
# `llm_extractor.NON_FOOD`'s value, not an import of it: `llm_extractor.py` is owned by a
# sibling lane this round and is not in the set of its names this module may rely on
# (`ProductResolution.resolve`, `ResolvableLine`, `Resolution`, `extract_json_object`,
# `CategoryOption`). Kept identical so the two prompts agree on the sentinel.
NON_FOOD = "household"


class ReceiptNotFound(LookupError):
    """No receipt with this id."""


class LineNotFound(LookupError):
    """No line with this id on this receipt."""


class ReceiptNotReanalysable(Exception):
    """The receipt is not in a state a single line can be re-asked about."""


class InvalidHint(ValueError):
    """The hint is longer than the service accepts."""


class ReanalyseUnavailable(Exception):
    """The model gateway could not be reached, or rejected the request."""


class ReanalyseTimedOut(Exception):
    """The model did not answer within the budget."""


class InvalidModelAnswer(Exception):
    """The model answered, but not usably: no generic name, or an unknown category."""


INSTRUCTIONS = """Re-read one receipt line. Answer with its generic name and its category only.

g = the simple generic English name a home cook would write on a shopping list. No brand,
size, fat content, percentage or flavour-neutral variant. Always singular: "Apple", not
"Apples". A different kind of food is a different product: oat milk is not milk, a cherry
tomato is not a tomato, baking chocolate is not chips.
c = the best category id for it, or "{non_food}" if it is household or cleaning, not food at
all, or null if nothing fits. Categories: {categories}.
{hint_rule}
Printed line: {printed}
{price_line}{locale_line}{hint_line}
Answer with JSON only: {{"g": "<generic name>", "c": "<category id>", "{non_food}" or null}}."""

HINT_RULE = (
    "The cook may give a hint saying what the line actually is. A hint outranks the "
    "printed text - trust the cook's word over what was printed."
)


@dataclass(frozen=True)
class LineRequest:
    """What the prompt needs about the one line being re-asked about."""

    printed: str
    price: float | None
    language: str | None
    country: str | None
    hint: str | None


def build_prompt(request: LineRequest, categories: list[CategoryOption]) -> str:
    listed = ", ".join(f"{c.id} ({c.name})" for c in categories) or "none"
    price_line = f"Price: {request.price}\n" if request.price is not None else ""
    locale_bits = [part for part in (request.language, request.country) if part]
    locale_line = f"Language/country: {'/'.join(locale_bits)}\n" if locale_bits else ""
    hint_line = f"The cook's hint: {request.hint}\n" if request.hint else ""
    return INSTRUCTIONS.format(
        non_food=NON_FOOD,
        categories=listed,
        hint_rule=HINT_RULE,
        printed=request.printed,
        price_line=price_line,
        locale_line=locale_line,
        hint_line=hint_line,
    )


def parse_answer(content: str, category_ids: set[str]) -> tuple[str, str | None, bool]:
    """The model's (generic name, category id or None, non_food) for this one line.

    Raises:
        InvalidModelAnswer: no usable `g`, or `c` is neither a known id, the non-food
            value, nor null.
    """
    data = extract_json_object(content)
    generic = data.get("g")
    generic = " ".join(str(generic).split()) if isinstance(generic, str) else ""
    if not generic:
        raise InvalidModelAnswer("The model did not return a usable name for this line")

    raw_category = data.get("c")
    by_fold = {known.casefold(): known for known in category_ids}
    if raw_category is None:
        return generic, None, False
    if not isinstance(raw_category, str):
        raise InvalidModelAnswer("The model's category is not usable")
    folded = raw_category.casefold()
    if folded == NON_FOOD.casefold():
        return generic, None, True
    category = by_fold.get(folded)
    if category is None:
        raise InvalidModelAnswer(
            f"The model answered an unknown category '{raw_category}'"
        )
    return generic, category, False


def _find_line(
    structured: dict[str, Any] | None, line_id: UUID
) -> tuple[int, dict[str, Any]] | None:
    lines = (structured or {}).get("lines")
    if not isinstance(lines, list):
        return None
    wanted = str(line_id)
    for index, candidate in enumerate(lines):
        if (
            isinstance(candidate, dict)
            and candidate.get("name")
            and str(candidate.get("line_id") or "") == wanted
        ):
            return index, candidate
    return None


async def _ask_model(prompt: str) -> str:
    """One small chat completion for this line alone.

    Raises:
        ReanalyseUnavailable: the gateway rejected the key, or could not be reached.
        ReanalyseTimedOut: the request did not answer within the budget.
    """
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
    }
    if settings.LLM_REASONING_STRENGTH:
        payload["chat_template_kwargs"] = {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }

    budget = settings.LLM_ESTIMATE_TIMEOUT
    try:
        async with httpx.AsyncClient(timeout=budget) as client:
            response = await post_chat(client, payload, budget=budget)
            response.raise_for_status()
            body = response.json()
    except LLMAuthError as exc:
        raise ReanalyseUnavailable(str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise ReanalyseTimedOut(
            "The model did not answer in time; this line is unchanged"
        ) from exc
    except httpx.HTTPError as exc:
        raise ReanalyseUnavailable(
            f"The model gateway is unavailable: {exc!r}"
        ) from exc

    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise InvalidModelAnswer("The model's response had no content") from exc
    return cast(str, content)


def _structured_of(receipt: Receipt) -> dict[str, Any] | None:
    return cast(
        "dict[str, Any] | None",
        receipt.ocr_structured if isinstance(receipt.ocr_structured, dict) else None,
    )


def _check_reanalysable(receipt: Receipt | None, receipt_id: UUID) -> Receipt:
    """404/409, shared by the unlocked read and the locked re-check (F1)."""
    if receipt is None:
        raise ReceiptNotFound(f"Receipt '{receipt_id}' not found")
    if receipt.processing_status != ReceiptStatus.COMPLETED:
        raise ReceiptNotReanalysable(
            f"Receipt is not reviewable (status {receipt.processing_status})"
        )
    return receipt


async def reanalyse_line(
    db: AsyncSession, receipt_id: UUID, line_id: UUID, hint: str | None
) -> ExtractedItem:
    """Re-ask the model for one line's generic name, category and match.

    Nothing is learned: no alias, synonym or product is created or changed.

    The receipt row is **not** locked while the model answers (up to
    `settings.LLM_ESTIMATE_TIMEOUT`, plus a possible second call if resolution asks the
    model to pick a product): a lock held that long would block confirm, and any other
    re-analyse, on the same receipt for no reason - nothing here needs exclusivity until
    the write. The row is re-read `FOR UPDATE` only once the answer is in hand, the
    receipt and the line are re-checked (another confirm or re-read could have run while
    this one was waiting), and only then is anything written.

    Raises:
        ReceiptNotFound: no receipt with this id.
        LineNotFound: no line with this id on this receipt.
        ReceiptNotReanalysable: the receipt is not `completed`.
        InvalidHint: the hint is longer than allowed.
        ReanalyseUnavailable: the model gateway could not be reached or answered (503).
        ReanalyseTimedOut: the model did not answer in time (504).
        InvalidModelAnswer: the model's answer was unusable (502); the line is unchanged.
    """
    if hint is not None and len(hint) > HINT_MAX_LENGTH:
        raise InvalidHint(f"The hint is longer than {HINT_MAX_LENGTH} characters")

    # Phase 1: read only, no lock. Builds the prompt and asks the model.
    receipt = _check_reanalysable(await db.get(Receipt, receipt_id), receipt_id)
    structured = _structured_of(receipt)
    found = _find_line(structured, line_id)
    if found is None or structured is None:
        raise LineNotFound(f"Receipt has no line '{line_id}'")
    _, line = found

    categories = [
        CategoryOption(id=str(c.id), name=str(c.display_name))
        for c in await get_categories(db)
    ]
    category_ids = {c.id for c in categories}

    price = line.get("price")
    request = LineRequest(
        printed=str(line["name"]),
        price=float(price) if isinstance(price, int | float) else None,
        language=structured.get("language")
        if isinstance(structured.get("language"), str)
        else None,
        country=structured.get("country")
        if isinstance(structured.get("country"), str)
        else None,
        hint=hint,
    )
    prompt = build_prompt(request, categories)

    started = time.monotonic()
    content = await _ask_model(prompt)
    generic, category, non_food = parse_answer(content, category_ids)

    # Resolution reads alias/name keys and, only for a line none of those settle, asks
    # the model to pick from a shortlist (`ProductResolution._select`) - another call
    # with no lock held, same reasoning as above.
    chain = (
        normalize_store_chain(str(receipt.store_chain) if receipt.store_chain else None)
        or UNKNOWN_CHAIN
    )
    remembered = await known_non_food(db, None)
    resolvable = ResolvableLine(
        line_id=str(line_id),
        printed=request.printed,
        generic=generic,
        category=category,
    )
    resolutions = await ProductResolution(db).resolve(
        [resolvable], chain=chain, non_food=remembered
    )
    resolution = resolutions[str(line_id)]
    non_food = non_food or resolution.non_food

    # Phase 2: lock, re-check, write. Everything above only computed an answer; nothing
    # was assumed still true until now. `populate_existing` matters here: `receipt` is
    # already in this session's identity map from phase 1, and without it SQLAlchemy
    # would hand back that same Python object unrefreshed - the lock would be real at
    # the database level, but the re-check above it would still be reading phase 1's
    # stale `ocr_structured`, exactly what phase 2 exists to not do.
    receipt = _check_reanalysable(
        (
            await db.execute(
                select(Receipt)
                .where(Receipt.id == receipt_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none(),
        receipt_id,
    )
    structured = _structured_of(receipt)
    found = _find_line(structured, line_id)
    if found is None or structured is None:
        raise LineNotFound(f"Receipt has no line '{line_id}'")
    index, line = found

    line["generic_name"] = generic
    line["category"] = None if non_food else category
    line["non_food"] = non_food
    line["product_id"] = str(resolution.product.id) if resolution.product else None
    line["product_name"] = (
        str(resolution.product.canonical_name) if resolution.product else None
    )
    line["product_storage_type"] = (
        str(resolution.product.storage_type) if resolution.product else None
    )
    line["match_source"] = resolution.source if resolution.product else None
    # No score ever decided anything for this line (H13); a stale one from the first
    # read would otherwise survive a re-analyse that found nothing (receipt_processing.py
    # resets the same pair when it writes a line).
    line["match_score"] = None
    line["match_confidence"] = None
    line["resolution"] = resolution.as_dict()
    line["reanalysed"] = True
    line["reanalyse_hint"] = hint

    flag_modified(receipt, "ocr_structured")
    await db.commit()
    await db.refresh(receipt)

    logger.info(
        "Receipt line re-analysed",
        extra={
            "receipt_id": str(receipt_id),
            "line_id": str(line_id),
            "had_hint": hint is not None,
            "seconds": round(time.monotonic() - started, 1),
        },
    )

    await broadcast_receipt_status(
        receipt_id=cast(UUID, receipt.id),
        status="completed",
        items_extracted=int(receipt.items_extracted or 0),
        items_matched=int(receipt.items_matched or 0),
    )

    items = items_from_structured(_structured_of(receipt))
    for item in items:
        if item.index == index:
            return item
    # The line was found above by its own line_id, so this cannot happen in practice -
    # but items_from_structured re-derives from the committed row, not the dict we just
    # mutated, so a defensive error beats a confusing IndexError on items[0].
    raise LineNotFound(f"Receipt has no line '{line_id}' after re-analysis")
