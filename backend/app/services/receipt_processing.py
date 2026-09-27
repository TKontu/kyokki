"""Receipt processing service - orchestrates text or image extraction and product matching.

Pipeline:
1. Read the receipt: PDF text (pdfplumber) or image OCR (MinerU); when MinerU is unavailable or
   finds no text, the image is read directly by the vision-capable LLM.
2. Extract product lines, store, date and category suggestions with the LLM.
3. On text, check every priced line was accounted for and recover what was not (Q27);
   on text and vision, check the line totals against the printed total.
4. Resolve each line to a product.
5. Store the structured result on the receipt.
"""

import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import anyio
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.category import get_categories
from app.models.receipt import Receipt
from app.parsers.amounts import (
    amount_style,
    continues_a_name,
    detail_count,
    explaining_pair,
    is_detail,
    line_amount,
    strip_amount,
)
from app.parsers.base import ExtractedLine, OtherLine, ReceiptExtraction
from app.parsers.heuristic import parse_receipt_text
from app.parsers.profiles import profile_for
from app.schemas.receipt import ReceiptStatus
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.llm_extractor import (
    CategoryOption,
    LLMExtractionError,
    extract_from_image,
    extract_from_text,
    extract_unaccounted_lines,
    number_receipt_lines,
)
from app.services.matching_service import normalize_receipt_name
from app.services.non_food import known_non_food
from app.services.ocr_service import (
    OCRUnavailableError,
    content_type_for,
    extract_text_from_receipt,
    is_pdf,
)
from app.services.product_resolution import (
    ProductResolution,
    Resolution,
    ResolvableLine,
    canonical_names,
)
from app.services.store_chain import normalize_store_chain
from app.services.units import grams_from_name

logger = get_logger(__name__)

MAX_ERROR_CHARS = 500  # stored on the receipt and shown to the user
SUPERSEDED = "The receipt stopped processing (failed as stale or queued again) before the read finished"


def _line_ids_by_name(structured: object) -> dict[str, list[str]]:
    """Line ids already stored for this receipt, grouped by normalised printed name.

    A re-read produces a fresh list of lines; matching them back by printed name keeps
    the identity of every line that was there before, so edits and non-food memory
    survive (H12). Repeats of one printed name are handed out in order.
    """
    if not isinstance(structured, dict):
        return {}
    lines = structured.get("lines")
    if not isinstance(lines, list):
        return {}
    by_name: dict[str, list[str]] = {}
    for line in lines:
        if not isinstance(line, dict):
            continue
        line_id, name = line.get("line_id"), line.get("name")
        if line_id and name:
            by_name.setdefault(normalize_receipt_name(str(name)), []).append(
                str(line_id)
            )
    return by_name


def _line_id_for(name: str, previous: dict[str, list[str]]) -> str:
    """Reuse this printed name's next unused id, or mint one."""
    waiting = previous.get(normalize_receipt_name(name))
    if waiting:
        return waiting.pop(0)
    return str(uuid4())


# --- Completeness (Q27) --------------------------------------------------------------
#
# The first model read of a 15-line K-Citymarket receipt returned 6 products and nothing
# said so. Receipts come from any shop, country and language, so the check does not parse
# the receipt itself. Every prompt line is numbered; a line that carries an amount at its end
# (`app.parsers.amounts`, locale-neutral) must be accounted for, either by a product that
# cites it in `l` or by an entry in `x` (a priced line that is not a product). A count or
# weight line counts as a product's own line only when that product cites it, or when its
# printed numbers multiply to that product's line total: adjacency alone proves nothing, and
# a missed "7UP 1,5L 2,49" under another product is not that product's detail line.
#
# Unaccounted priced lines, with their unpriced neighbours as context, get one targeted
# re-read without the catalog block. What is still unaccounted becomes a row as printed
# (`raw_line`) that keeps its amount, for the cook to decide. An optional country or
# language profile adds evidence only about lines the model neither cited nor listed: a line
# the model accounted for is the model's call. The receipt's own arithmetic (line totals
# against the printed total) is checked on the text and vision paths.

# Beyond this difference, in cents, the line totals do not add up to the printed total
_SUM_TOLERANCE_CENTS = 5
_FUZZY_NAME = 90
# Kinds whose amount the receipt adds to or takes from the product lines
_SIGNED_KINDS = ("discount", "deposit", "fee")


@dataclass
class _Receipt:
    """The numbered lines of one text receipt and the amount each priced line carries."""

    lines: dict[int, str]
    amounts: dict[int, float]

    @classmethod
    def of(cls, text: str) -> "_Receipt":
        numbered = number_receipt_lines(text)
        lines = {n: line for n, line in numbered if n is not None}
        style = amount_style(lines.values())
        amounts = {
            n: amount
            for n, line in lines.items()
            if (amount := line_amount(line, style)) is not None
        }
        return cls(lines=lines, amounts=amounts)

    def name(self, n: int) -> str:
        return normalize_receipt_name(strip_amount(self.lines[n]))


def _cite_by_name(
    product: ExtractedLine, receipt: _Receipt, free: Iterable[int]
) -> list[int]:
    """The line an answer without line numbers most likely came from, or none."""
    target = normalize_receipt_name(product.name)
    free = sorted(free)
    for n in free:
        if receipt.name(n) == target:
            return [n]
    best, best_score = None, 0.0
    for n in free:
        score = fuzz.ratio(receipt.name(n), target)
        if score > best_score:
            best, best_score = n, score
    return [best] if best is not None and best_score >= _FUZZY_NAME else []


def _split_repeats(
    products: list[ExtractedLine], receipt: _Receipt
) -> list[ExtractedLine]:
    """One entry citing two identical priced lines ("MAITO 1,29" twice) is two products."""
    result: list[ExtractedLine] = []
    for product in products:
        cited = [n for n in product.source_lines if n in receipt.lines]
        names = [
            n for n in cited if n in receipt.amounts and not is_detail(receipt.lines[n])
        ]
        repeats = len(names) > 1 and len({receipt.name(n) for n in names}) == 1
        if not repeats:
            result.append(product)
            continue
        count = len(names)
        quantity = product.quantity
        if quantity >= count and quantity % count == 0:
            quantity = quantity / count
        for i, n in enumerate(names):
            details = [m for m in cited if m not in names] if i == 0 else []
            result.append(
                product.model_copy(
                    update={
                        "source_lines": sorted([n, *details]),
                        "price": receipt.amounts[n],
                        "quantity": quantity,
                    }
                )
            )
    return result


def _twin(n: int, receipt: _Receipt, taken: set[int], own: list[int]) -> int | None:
    """The next free line printed exactly like line ``n``."""
    name = receipt.name(n)
    for m in sorted(receipt.lines):
        if m not in taken and m not in own and m != n and receipt.name(m) == name:
            return m
    return None


def _cite(
    products: list[ExtractedLine], receipt: _Receipt, taken: set[int]
) -> set[int]:
    """Record each product's valid source lines, falling back to its name; return them.

    A second entry citing the same line as an earlier one is that line's identical twin
    when the receipt prints one ("MAITO 1,29" twice, both answered as line 2).
    """
    cited: set[int] = set()
    for product in products:
        valid = [n for n in product.source_lines if n in receipt.lines]
        if valid and all(n in cited | taken for n in valid):
            twins = [_twin(n, receipt, cited | taken, valid) for n in valid]
            if all(t is not None for t in twins):
                valid = sorted(t for t in twins if t is not None)
        if not valid:
            free = (n for n in receipt.lines if n not in taken | cited)
            valid = _cite_by_name(product, receipt, free)
        product.source_lines = valid
        cited.update(valid)
    return cited


def _attach_details(
    products: list[ExtractedLine], receipt: _Receipt, open_lines: set[int]
) -> set[int]:
    """Uncited count or weight lines whose arithmetic proves they belong to a product.

    A detail line next to a product's cited line is that product's when its numbers
    multiply to the product's line total ("2 x 1,49" beside a 2,98), or when it carries
    that line total itself ("0,845 kg x 1,99 1,68" under a name line). The product then
    cites it. Returns the lines attached.
    """
    attached: set[int] = set()
    for product in products:
        if product.price is None:
            continue
        for n in list(product.source_lines):
            for m in (n - 1, n + 1):
                if m not in open_lines or m in attached:
                    continue
                text = receipt.lines[m]
                amount = receipt.amounts.get(m)
                own_total = amount is not None and abs(amount - product.price) < 0.005
                if is_detail(text) and (
                    own_total or explaining_pair(text, product.price) is not None
                ):
                    attached.add(m)
                    product.source_lines = sorted({*product.source_lines, m})
    return attached


def _accounted_others(
    others: list[OtherLine], receipt: _Receipt, adds_up: bool
) -> set[int]:
    """Lines the answer listed as not products.

    The rule for a priced line listed as kind `other` (Q27 verdict #3): it is re-read unless
    the model's own arithmetic - its line totals with its discounts, deposits and fees, and
    its tax on a tax-exclusive receipt - matches the printed total it read, a total it also
    listed in `x` as a line of kind `total`. Then the money on the receipt is all in the
    products, so the `other` line (a loyalty sum, a card slip) is not a product by
    construction. Without a total, with a total the sums miss, or with `t` read from a line
    the model did not call the total, it is re-read.
    """
    return {
        o.line
        for o in others
        if o.line in receipt.lines
        and (adds_up or o.kind != "other" or o.line not in receipt.amounts)
    }


def _raw_group(n: int, receipt: _Receipt, free: set[int]) -> list[int]:
    """Priced line ``n`` and the unaccounted lines that are provably the same item."""
    lines, amounts = receipt.lines, receipt.amounts
    group = {n}
    before, after = n - 1, n + 1

    def unpriced_name(m: int) -> bool:
        return m in free and m not in amounts and not is_detail(lines[m])

    if is_detail(lines[n]):
        # A count line printed before or after its priced name: its numbers make that total
        partner = next(
            (
                m
                for m in (after, before)
                if m in free
                and m in amounts
                and not is_detail(lines[m])
                and explaining_pair(lines[n], amounts[m]) is not None
            ),
            None,
        )
        if partner is not None:
            group.add(partner)
        elif unpriced_name(before) and explaining_pair(lines[n], amounts[n]):
            # "0,845 kg x 1,99 1,68" carries its own total; its name is the line above
            group.add(before)
    else:
        for m in (before, after):
            if (
                m in free
                and m not in amounts
                and is_detail(lines[m])
                and explaining_pair(lines[m], amounts[n]) is not None
            ):
                group.add(m)
        # Only a name's own first half joins it: a line that the priced line continues
        if unpriced_name(before) and continues_a_name(lines[n]):
            group.add(before)
    return sorted(group)


def _raw_line(group: list[int], receipt: _Receipt) -> ExtractedLine:
    """A leftover item as printed, with the amount it was cut from, for the cook to decide."""
    texts = {n: receipt.lines[n] for n in group}
    names = [strip_amount(t) for t in texts.values() if not is_detail(t)]
    name = " ".join(part for part in names if part) or " ".join(
        part for part in (strip_amount(t) for t in texts.values()) if part
    )
    priced = [n for n in group if n in receipt.amounts]
    price_line = next((n for n in priced if not is_detail(texts[n])), priced[0])
    price = receipt.amounts[price_line]
    # "2 x 1,49" with its 2,98: the missed item comes back as two, not one (verdict #11)
    count = next(
        (
            c
            for n in group
            if is_detail(texts[n]) and (c := detail_count(texts[n], price)) is not None
        ),
        None,
    )
    return ExtractedLine(
        name=name or " ".join(texts.values()),
        quantity=float(count or 1),
        source_lines=group,
        price=price,
        recovered="raw_line",
    )


def _raw_rows(still: set[int], receipt: _Receipt) -> list[ExtractedLine]:
    """One row per leftover priced item; unpriced lines join only an item they belong to."""
    rows: list[ExtractedLine] = []
    free = set(still)
    for n in sorted(still):
        if n not in free or n not in receipt.amounts:
            continue
        group = _raw_group(n, receipt, free)
        free -= set(group)
        rows.append(_raw_line(group, receipt))
    return rows


def receipt_arithmetic(
    products: list[ExtractedLine],
    others: list[OtherLine],
    total: float | None,
    tax_exclusive: bool = False,
) -> tuple[float | None, bool]:
    """Σ line totals plus signed discounts, deposits and fees; and whether it misses the total.

    Works for any currency and on the vision path. A detail line's unit price is never
    part of it: only a product's `p`, its line total, is summed. Some receipts print a
    discount that is already taken off the line total (S-kaupat's NORM./ALENNUS pair),
    others take it off at the end; a receipt matching either way is not a mismatch. Tax
    lines count only when the model says the line totals leave the tax out (`te`, as on a
    US receipt); elsewhere the tax is already inside every line total.
    """
    prices = [p.price for p in products if p.price is not None]
    if not prices:
        return None, False
    kinds = _SIGNED_KINDS + (("tax",) if tax_exclusive else ())
    amounts = [o for o in others if o.kind in kinds and o.amount is not None]
    discounts = sum(-abs(o.amount or 0) for o in amounts if o.kind == "discount")
    charges = sum(o.amount or 0 for o in amounts if o.kind != "discount")
    # Compared in whole cents, so float noise never decides a mismatch
    sum_cents = round((sum(prices) + charges + discounts) * 100)
    if total is None:
        return sum_cents / 100, False
    total_cents = round(total * 100)
    tolerance = max(_SUM_TOLERANCE_CENTS, abs(total_cents) / 100)
    if abs(sum_cents - total_cents) <= tolerance:
        return sum_cents / 100, False
    net_cents = round((sum(prices) + charges) * 100)
    if discounts and abs(net_cents - total_cents) <= tolerance:
        return net_cents / 100, False
    return sum_cents / 100, True


@dataclass
class ReadOutcome:
    """What reading one receipt produced, beyond the extraction itself (Q27)."""

    ocr_text: str | None
    extraction: ReceiptExtraction
    note: str | None = None
    completeness: dict[str, Any] | None = None
    raw_completions: dict[str, str] = field(default_factory=dict)


def _completeness(
    *,
    text_lines: int | None,
    model_lines: int,
    recovered_by_retry: int = 0,
    recovered_raw_lines: int = 0,
    invalid_entries: int = 0,
    unaccounted_lines: int = 0,
    items_sum: float | None = None,
    receipt_total: float | None = None,
    profile: str | None = None,
    profile_only_lines: int = 0,
) -> dict[str, Any]:
    return {
        "text_lines": text_lines,
        "model_lines": model_lines,
        "recovered_by_retry": recovered_by_retry,
        "recovered_raw_lines": recovered_raw_lines,
        "invalid_entries": invalid_entries,
        "unaccounted_lines": unaccounted_lines,
        "items_sum": items_sum,
        "receipt_total": receipt_total,
        "profile": profile,
        "profile_only_lines": profile_only_lines,
    }


def _arithmetic_note(
    items_sum: float | None, total: float | None, off: bool
) -> str | None:
    if not off or items_sum is None or total is None:
        return None
    return f"Line totals add up to {items_sum:.2f} but the receipt total is {total:.2f}"


def _join_notes(*notes: str | None) -> str | None:
    kept = [note for note in notes if note]
    return "; ".join(kept)[:MAX_ERROR_CHARS] if kept else None


def vision_outcome(extraction: ReceiptExtraction) -> ReadOutcome:
    """The vision path has no text to account for; the arithmetic still applies.

    Its `x` has no line numbers but still carries the discounts, deposits and fees, so a
    photographed receipt with a deposit adds up like a text one (Q27 verdict #6).
    """
    items_sum, off = receipt_arithmetic(
        extraction.lines,
        extraction.other_lines,
        extraction.receipt_total,
        extraction.tax_exclusive,
    )
    return ReadOutcome(
        ocr_text=None,
        extraction=extraction,
        note=_arithmetic_note(items_sum, extraction.receipt_total, off),
        completeness=_completeness(
            text_lines=None,
            model_lines=len(extraction.lines),
            invalid_entries=extraction.invalid_entries,
            items_sum=items_sum,
            receipt_total=extraction.receipt_total,
        ),
        raw_completions=_raw(extraction, "raw_completion"),
    )


def _raw(extraction: ReceiptExtraction | None, key: str) -> dict[str, str]:
    if extraction is None or extraction.raw_completion is None:
        return {}
    return {key: extraction.raw_completion}


def _failed_raw(exc: BaseException, key: str) -> dict[str, str]:
    """The unusable answer an extraction error carries, if any (Q27 verdict #13)."""
    raw = getattr(exc, "raw_completion", None)
    return {key: raw} if isinstance(raw, str) else {}


def _profile_evidence(
    extraction: ReceiptExtraction,
    text: str,
    accounted: set[int],
    receipt_id: str | None,
) -> tuple[str | None, set[int], int]:
    """(profile name, lines it says hold products the model never accounted for, how many).

    A profile product counts only when none of its lines is cited by a model product or
    listed in `x`: the profile never overrides the model's reading of a line (verdict #2).
    """
    profile = profile_for(extraction.country, extraction.language)
    if profile is None:
        return None, set(), 0
    name = profile.language or profile.country
    try:
        found = profile.product_lines(number_receipt_lines(text))
    except Exception as exc:  # a profile is evidence; it must never fail a receipt
        logger.warning(
            "Receipt profile failed, continuing without it",
            extra={"receipt_id": receipt_id, "profile": name, "error": repr(exc)},
        )
        return None, set(), 0
    missing = [p for p in found if not accounted.intersection(p.line_numbers)]
    return name, {n for p in missing for n in p.line_numbers}, len(missing)


def _place_retry_products(
    retry: ReceiptExtraction,
    receipt: _Receipt,
    open_lines: set[int],
    receipt_id: str | None,
) -> tuple[list[ExtractedLine], int]:
    """The re-read's products placed on the lines it was asked about, and how many were not.

    A product citing only lines outside the question, or already accounted for, cannot be
    placed; it is counted in `invalid_entries` and logged, never dropped silently (verdict
    #20). Its line, if still open, becomes a raw row.
    """
    placed: list[ExtractedLine] = []
    misplaced = 0
    free = set(open_lines)
    for product in _split_repeats(list(retry.lines), receipt):
        valid = [n for n in product.source_lines if n in free]
        if not valid and not product.source_lines:
            valid = _cite_by_name(product, receipt, free)
        if not valid:
            misplaced += 1
            logger.warning(
                "Re-read product cites no open line; not used",
                extra={
                    "receipt_id": receipt_id,
                    "cited": product.source_lines,
                    "open_lines": sorted(free),
                },
            )
            continue
        product.source_lines = valid
        product.recovered = "model_retry"
        placed.append(product)
        free -= set(valid)
    return placed, misplaced


async def reconcile_text_read(
    text: str,
    extraction: ReceiptExtraction,
    categories: Sequence[CategoryOption],
    receipt_id: str | None = None,
) -> ReadOutcome:
    """Make sure every priced line of a text receipt is accounted for (Q27).

    Model products the checks cannot place are kept as read; nothing is dropped, and a
    failing re-read never fails the receipt.
    """
    receipt = _Receipt.of(text)
    lines, priced = receipt.lines, set(receipt.amounts)
    first = _split_repeats(list(extraction.lines), receipt)

    cited = _cite(first, receipt, set())
    listed = {o.line for o in extraction.other_lines if o.line in lines}
    first_sum, first_off = receipt_arithmetic(
        first,
        extraction.other_lines,
        extraction.receipt_total,
        extraction.tax_exclusive,
    )
    # The total the sums must reach is one the model also listed as a `total` line: a
    # subtotal or a loyalty sum read as `t` proves nothing (verdict #3)
    listed_totals = {
        round(o.amount * 100)
        for o in extraction.other_lines
        if o.kind == "total" and o.amount is not None and o.line in lines
    }
    adds_up = (
        first_sum is not None
        and extraction.receipt_total is not None
        and not first_off
        and round(extraction.receipt_total * 100) in listed_totals
    )
    accounted = cited | _accounted_others(extraction.other_lines, receipt, adds_up)
    # Only a line with an amount on it has to be accounted for; the model lists no other
    # non-product line, which keeps its answer short (a 49-line read ran past 180 s)
    open_priced = priced - accounted
    attached = _attach_details(first, receipt, open_priced)
    open_priced -= attached
    cited |= attached
    accounted |= attached
    profile, profile_lines, profile_only = _profile_evidence(
        extraction, text, cited | listed, receipt_id
    )
    unaccounted = open_priced | (profile_lines - accounted)
    # An unpriced neighbour of a line that really is unaccounted - a wrapped name, a name
    # above its price line, a weight line - goes to the re-read with it as context
    context = unaccounted | {
        m
        for n in unaccounted & priced
        for m in (n - 1, n + 1)
        if m in lines and m not in priced and m not in cited and m not in listed
    }

    retry: ReceiptExtraction | None = None
    raw_retry: dict[str, str] = {}
    recovered: list[ExtractedLine] = []
    misplaced = 0
    still = set(context)
    if unaccounted & priced:
        try:
            retry = await extract_unaccounted_lines(
                [(n, lines[n]) for n in sorted(context)], categories
            )
        except Exception as exc:  # a bad re-read never fails the receipt (verdict #19)
            logger.warning(
                "Targeted re-read failed; listing unaccounted lines as printed",
                extra={"receipt_id": receipt_id, "error": repr(exc)},
            )
            raw_retry = _failed_raw(exc, "raw_completion_retry")
    if retry is not None:
        recovered, misplaced = _place_retry_products(retry, receipt, still, receipt_id)
        still -= {n for p in recovered for n in p.source_lines}
        # A line the re-read, shown it on purpose and without the catalog, still lists
        # as not a product is accounted for
        still -= {o.line for o in retry.other_lines if o.line in context}
        still -= _attach_details(recovered, receipt, still)

    raw_rows = _raw_rows(still, receipt)

    others = list(extraction.other_lines)
    if retry is not None:
        others += [o for o in retry.other_lines if o.line in context]
    final = first + recovered + raw_rows
    # A raw row keeps the amount it was cut from, so a recovered line alone never reads
    # as "something may be missing" (verdict #10)
    items_sum, off = receipt_arithmetic(
        final, others, extraction.receipt_total, extraction.tax_exclusive
    )
    extraction.lines = final
    # After recovery a priced line is left over only if no row took it (normally none)
    in_rows = {n for row in raw_rows for n in row.source_lines}
    left_over = {n for n in still if n in priced and n not in in_rows}
    missed = len(recovered) + len(raw_rows)
    note = _join_notes(
        f"{missed} of {len(final)} lines were not read by the model and were recovered"
        if missed
        else None,
        _arithmetic_note(items_sum, extraction.receipt_total, off),
    )
    if missed or off:
        logger.warning(
            "Receipt read was incomplete",
            extra={
                "receipt_id": receipt_id,
                "model_lines": len(first),
                "recovered_by_retry": len(recovered),
                "recovered_raw_lines": len(raw_rows),
                "unaccounted_before_recovery": len(unaccounted),
                "unaccounted_lines": len(left_over),
                "items_sum": items_sum,
                "receipt_total": extraction.receipt_total,
            },
        )
    return ReadOutcome(
        ocr_text=text,
        extraction=extraction,
        note=note,
        completeness=_completeness(
            # contract ruling 1: product rows, not text lines; "9 of 15" on the K receipt
            text_lines=len(final),
            model_lines=len(first),
            recovered_by_retry=len(recovered),
            recovered_raw_lines=len(raw_rows),
            invalid_entries=extraction.invalid_entries
            + (retry.invalid_entries if retry else 0)
            + misplaced,
            unaccounted_lines=len(left_over),
            items_sum=items_sum,
            receipt_total=extraction.receipt_total,
            profile=profile,
            profile_only_lines=profile_only,
        ),
        raw_completions=_raw(extraction, "raw_completion")
        | _raw(retry, "raw_completion_retry")
        | raw_retry,
    )


@dataclass
class ReadTimings:
    """How long the two slow steps took.

    MVP-R4 records OCR time and model time per receipt, and neither is stored on the row, so
    they are measured here and published on the completion log line.
    """

    ocr_seconds: float = field(default=0.0)
    llm_seconds: float = field(default=0.0)

    @contextmanager
    def ocr(self) -> Iterator[None]:
        started = time.monotonic()
        try:
            yield
        finally:
            self.ocr_seconds += time.monotonic() - started

    @contextmanager
    def llm(self) -> Iterator[None]:
        started = time.monotonic()
        try:
            yield
        finally:
            self.llm_seconds += time.monotonic() - started


@dataclass
class ProcessingResult:
    """Result of receipt processing pipeline."""

    success: bool
    ocr_text: str | None
    extraction: ReceiptExtraction | None
    # Line id -> how that line resolved. Empty when the read failed.
    resolutions: dict[str, Resolution]
    error: str | None = None


def _keep_failed_answer(row: Any, exc: BaseException) -> None:
    """Persist the unusable answer that failed the receipt, capped (Q27 verdict #13)."""
    raw = _failed_raw(exc, "raw_completion")
    if not raw:
        return
    previous = row.ocr_structured if isinstance(row.ocr_structured, dict) else {}
    row.ocr_structured = {**previous, **raw}


class ReceiptProcessingService:
    """Service for processing receipts through extraction → matching."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _read_receipt(
        self,
        receipt: Receipt,
        categories: list[CategoryOption],
        known_products: list[str],
        timings: ReadTimings,
    ) -> ReadOutcome:
        """Read the receipt, choosing text or vision input."""
        path = str(receipt.image_path)

        if is_pdf(path):
            with timings.ocr():
                pdf_text = await extract_text_from_receipt(path)
            return await self._read_text(
                receipt, pdf_text, categories, known_products, timings
            )

        text: str | None
        try:
            with timings.ocr():
                text = await extract_text_from_receipt(path)
        except OCRUnavailableError as exc:
            logger.warning(
                "OCR unavailable, reading the image with the vision model",
                extra={"receipt_id": str(receipt.id), "error": str(exc)},
            )
            text = None

        if text and text.strip():
            return await self._read_text(
                receipt, text, categories, known_products, timings
            )

        if text is not None:
            logger.warning(
                "OCR returned no text, reading the image with the vision model",
                extra={"receipt_id": str(receipt.id)},
            )
        image = await anyio.Path(path).read_bytes()
        # No text to fall back on: a failing vision call fails the receipt
        with timings.llm():
            extraction = await extract_from_image(
                image, content_type_for(path), categories, known_products
            )
        return vision_outcome(extraction)

    async def _read_text(
        self,
        receipt: Receipt,
        text: str,
        categories: list[CategoryOption],
        known_products: list[str],
        timings: ReadTimings,
    ) -> ReadOutcome:
        """Extract with the model and account for every line; else use the heuristic parser.

        The parser only helps when the text has product lines; otherwise the model's error
        stands and the receipt fails as before (MVP-R3b). A model answer that leaves lines
        out is completed by `reconcile_text_read` (Q27).
        """
        try:
            with timings.llm():
                extraction = await extract_from_text(text, categories, known_products)
        except LLMExtractionError as exc:
            fallback = parse_receipt_text(text)
            if not fallback.lines:
                raise
            logger.warning(
                "LLM extraction failed, using the heuristic parser",
                extra={"receipt_id": str(receipt.id), "error": str(exc)},
            )
            return ReadOutcome(
                ocr_text=text,
                extraction=fallback,
                note=f"Model unavailable: {exc}"[:MAX_ERROR_CHARS],
                completeness=_completeness(
                    text_lines=len(fallback.lines), model_lines=0
                ),
                raw_completions=_failed_raw(exc, "raw_completion"),
            )

        if not extraction.lines:
            fallback = parse_receipt_text(text)
            if fallback.lines:
                logger.warning(
                    "LLM found no products, using the heuristic parser",
                    extra={"receipt_id": str(receipt.id)},
                )
                return ReadOutcome(
                    ocr_text=text,
                    extraction=fallback,
                    note="Model found no products",
                    completeness=_completeness(
                        text_lines=len(fallback.lines),
                        model_lines=0,
                        invalid_entries=extraction.invalid_entries,
                    ),
                    raw_completions=_raw(extraction, "raw_completion"),
                )
        with timings.llm():
            return await reconcile_text_read(
                text, extraction, categories, receipt_id=str(receipt.id)
            )

    async def _still_processing(self, receipt_id: Any) -> bool:
        """Whether the row is still `processing`, locked until the result is committed.

        The lock makes `fail_stale` wait for this write instead of racing it.
        """
        status = (
            await self.db.execute(
                select(Receipt.processing_status)
                .where(Receipt.id == receipt_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        return status == ReceiptStatus.PROCESSING

    async def process_receipt(self, receipt: Receipt) -> ProcessingResult:
        """Process a receipt through the full pipeline and update the record."""
        row: Any = receipt  # Column-typed model: assign plain values
        receipt_id = receipt.id  # a rollback expires the object; keep its key
        timings = ReadTimings()
        started = time.monotonic()
        try:
            if receipt.processing_status != ReceiptStatus.PROCESSING:
                # Called directly rather than through the queue worker, which already claimed it
                row.processing_status = ReceiptStatus.PROCESSING
                row.processing_started_at = datetime.now(UTC)
                await self.db.commit()
                await broadcast_receipt_status(
                    receipt_id=receipt.id, status=ReceiptStatus.PROCESSING
                )
            logger.info(f"Starting processing for receipt {receipt.id}")

            categories = [
                CategoryOption(id=str(c.id), name=str(c.display_name))
                for c in await get_categories(self.db)
            ]
            # Catalog names are offered to the extraction prompt for reuse (H17 measures
            # dropping this); resolution no longer needs the catalog in memory.
            catalog = await canonical_names(self.db)
            # Names the cook has already called non-food; they win over a model that wavers
            remembered = await known_non_food(self.db, None)
            outcome = await self._read_receipt(receipt, categories, catalog, timings)
            ocr_text, extraction = outcome.ocr_text, outcome.extraction

            chain = normalize_store_chain(
                str(receipt.store_chain) if receipt.store_chain else None
            ) or normalize_store_chain(extraction.store_chain)

            stored_lines = []
            # Re-reading a receipt must not invalidate what the cook already edited, so
            # a printed name that was there before keeps its line_id (H12).
            previous_ids = _line_ids_by_name(receipt.ocr_structured)
            resolvable = [
                ResolvableLine(
                    line_id=_line_id_for(line.name, previous_ids),
                    printed=line.name,
                    generic=line.generic_name,
                    category=line.category,
                )
                for line in extraction.lines
            ]
            with timings.llm():
                resolutions = await ProductResolution(self.db).resolve(
                    resolvable, chain=chain, non_food=remembered
                )

            matched = 0
            for line, resolvable_line in zip(extraction.lines, resolvable, strict=True):
                resolution = resolutions[resolvable_line.line_id]
                product = resolution.product
                stored = line.model_dump(mode="json")
                if resolution.non_food:
                    stored["non_food"] = True
                if product is not None and product.avg_piece_grams is not None:
                    # The catalog already knows what one of these weighs; trust it over a
                    # fresh guess from the model (Q2).
                    stored["piece_grams"] = float(product.avg_piece_grams)
                # What one pack weighs (Q8): whatever the shop printed in the name, else
                # the catalog. The printed size is this purchase; the catalog's is a
                # product's usual pack, and "Helmitomaatti pikari 200g" matched to a
                # 250 g cherry tomato is still 200 g (Q27). The model is not asked - it
                # answered a `pk` field on 1 line of 49 and dragged the other estimates
                # down with it (docs/vLLM_MANUAL_TEST.md).
                pack_grams = grams_from_name(line.name)
                if (
                    pack_grams is None
                    and product is not None
                    and product.pack_grams is not None
                ):
                    pack_grams = float(product.pack_grams)
                if pack_grams is not None:
                    stored["pack_grams"] = pack_grams
                stored.update(
                    line_id=resolvable_line.line_id,
                    product_id=str(product.id) if product else None,
                    product_name=str(product.canonical_name) if product else None,
                    product_storage_type=str(product.storage_type) if product else None,
                    # No score decides anything any more; the field stays only so older
                    # clients keep parsing. H15 drops it from the review row.
                    match_score=None,
                    match_confidence=None,
                    match_source=resolution.source if product else None,
                    resolution=resolution.as_dict(),
                )
                stored_lines.append(stored)
                if product is not None:
                    matched += 1

            if not await self._still_processing(receipt_id):
                # `fail_stale` failed it while it was being read (or it was queued again):
                # the cook already sees that status, so this result is not written over it
                await self.db.rollback()
                logger.warning(
                    "Receipt is no longer processing; its read result is not written",
                    extra={
                        "receipt_id": str(receipt_id),
                        "total_seconds": round(time.monotonic() - started, 1),
                    },
                )
                return ProcessingResult(
                    success=False,
                    ocr_text=ocr_text,
                    extraction=extraction,
                    resolutions=resolutions,
                    error=SUPERSEDED,
                )

            row.processing_status = ReceiptStatus.COMPLETED
            row.error = None
            row.ocr_raw_text = ocr_text
            row.ocr_structured = {
                "method": extraction.method,
                "store_chain": extraction.store_chain,
                "purchase_date": extraction.purchase_date.isoformat()
                if extraction.purchase_date
                else None,
                "lines": stored_lines,
                "language": extraction.language,
                "country": extraction.country,
                "completeness": outcome.completeness,
                **outcome.raw_completions,
            }
            if outcome.note:
                row.ocr_structured["fallback_reason"] = outcome.note
            row.items_extracted = len(extraction.lines)
            row.items_matched = matched
            # Values the user entered at upload win over what was read from the receipt
            if chain and not receipt.store_chain:
                row.store_chain = chain
            if extraction.purchase_date and not receipt.purchase_date:
                row.purchase_date = extraction.purchase_date

            await self.db.commit()
            await self.db.refresh(receipt)

            await broadcast_receipt_status(
                receipt_id=receipt.id,
                status=ReceiptStatus.COMPLETED,
                items_extracted=receipt.items_extracted,
                items_matched=receipt.items_matched,
            )
            ocr_seconds = round(timings.ocr_seconds, 1)
            llm_seconds = round(timings.llm_seconds, 1)
            total_seconds = round(time.monotonic() - started, 1)
            # One line per receipt, with the numbers MVP-R4 records. The message repeats them
            # because the console formatter only shows extras when logging as JSON.
            logger.info(
                f"Receipt {receipt.id} read via {extraction.method} in {total_seconds}s "
                f"(OCR {ocr_seconds}s, model {llm_seconds}s): "
                f"{receipt.items_extracted} extracted, {receipt.items_matched} matched",
                extra={
                    "receipt_id": str(receipt.id),
                    "method": extraction.method,
                    "ocr_seconds": ocr_seconds,
                    "llm_seconds": llm_seconds,
                    "total_seconds": total_seconds,
                    "items_extracted": receipt.items_extracted,
                    "items_matched": receipt.items_matched,
                },
            )

            return ProcessingResult(
                success=True,
                ocr_text=ocr_text,
                extraction=extraction,
                resolutions=resolutions,
                error=None,
            )

        except Exception as e:
            error_msg = f"Receipt processing failed: {str(e)}"[:MAX_ERROR_CHARS]

            # The session may hold a failed flush; start clean before recording the failure
            await self.db.rollback()
            await self.db.refresh(receipt)
            if receipt.processing_status == ReceiptStatus.PROCESSING:
                row.processing_status = ReceiptStatus.FAILED
                row.error = error_msg
                _keep_failed_answer(row, e)
                await self.db.commit()

                await broadcast_receipt_status(
                    receipt_id=receipt.id, status=ReceiptStatus.FAILED, error=error_msg
                )
            logger.error(
                error_msg,
                exc_info=True,
                extra={
                    "receipt_id": str(receipt.id),
                    "error": error_msg,
                    "ocr_seconds": round(timings.ocr_seconds, 1),
                    "llm_seconds": round(timings.llm_seconds, 1),
                    "total_seconds": round(time.monotonic() - started, 1),
                },
            )

            return ProcessingResult(
                success=False,
                ocr_text=None,
                extraction=None,
                resolutions={},
                error=error_msg,
            )
