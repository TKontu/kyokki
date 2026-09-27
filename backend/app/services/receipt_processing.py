"""Receipt processing service - orchestrates text or image extraction and product matching.

Pipeline:
1. Read the receipt: PDF text (pdfplumber) or image OCR (MinerU); when MinerU is unavailable or
   finds no text, the image is read directly by the vision-capable LLM.
2. Extract product lines, store, date and category suggestions with the LLM.
3. On text, check every numbered line was accounted for and recover what was not (Q27);
   on text and vision, check the line totals against the printed total.
4. Resolve each line to a product.
5. Store the structured result on the receipt.
"""

import re
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import anyio
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.category import get_categories
from app.models.receipt import Receipt
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
# the receipt itself: the model numbers every prompt line to a product (`l`) or to a
# non-product kind (`x`), and a line in neither is unaccounted. Unaccounted lines get one
# targeted retry without the catalog block; what is still unaccounted and carries an amount
# is listed as the printed line for the cook to decide. An optional country or language
# profile adds evidence and never decides alone. The receipt's own arithmetic (line totals
# against the printed total) is checked on the text and vision paths.

# A price-like amount in any currency: digits with a two-digit `.` or `,` decimal part.
_AMOUNT = re.compile(r"(?<![\d.,])[-−]?\d+[.,]\d{2}(?!\d)")
# The same with an optional currency symbol or three-letter code, and a trailing minus
_AMOUNT_TEXT = re.compile(
    r"(?:[€$£¥]\s*)?(?<![\d.,])[-−]?\d+[.,]\d{2}(?!\d)-?"
    r"(?:\s*(?:[€$£¥]|[A-Z]{3}\b))?"
)
# A run of four or more letters in any script: something a name has and a detail line
# ("0,523 KG 1,99 €/KG", "2 x 1,49", "3 kom x 1,29") does not
_WORD = re.compile(r"[^\W\d_]{4,}")
# Beyond this difference the line totals do not add up to the printed total
_SUM_TOLERANCE = 0.05
_FUZZY_NAME = 90
# Kinds whose amount the receipt adds to or takes from the product lines
_SIGNED_KINDS = ("discount", "deposit", "fee")


def _has_amount(line: str) -> bool:
    return bool(_AMOUNT.search(line))


def _is_detail(line: str) -> bool:
    """A count, weight or unit-price line rather than a name, by shape alone."""
    return line[:1].isdigit() and not _WORD.search(line)


def _strip_amounts(line: str) -> str:
    return " ".join(_AMOUNT_TEXT.sub(" ", line).split())


def _layout(products: list[ExtractedLine], lines: dict[int, str]) -> str:
    """Whether this receipt prints detail lines after the name or before it.

    Read off the model's own multi-line products: no layout is assumed per shop.
    """
    after = before = 0
    for product in products:
        cited = [n for n in product.source_lines if n in lines]
        if len(cited) < 2:
            continue
        first, last = lines[cited[0]], lines[cited[-1]]
        if not _is_detail(first) and _is_detail(last):
            after += 1
        elif _is_detail(first) and not _is_detail(last):
            before += 1
    return "before" if before > after else "after"


def _cite_by_name(
    product: ExtractedLine, lines: dict[int, str], taken: set[int]
) -> list[int]:
    """The line an answer without line numbers most likely came from, or none."""
    target = normalize_receipt_name(product.name)
    free = [n for n in sorted(lines) if n not in taken]
    for n in free:
        if normalize_receipt_name(_strip_amounts(lines[n])) == target:
            return [n]
    best, best_score = None, 0.0
    for n in free:
        score = fuzz.ratio(normalize_receipt_name(_strip_amounts(lines[n])), target)
        if score > best_score:
            best, best_score = n, score
    return [best] if best is not None and best_score >= _FUZZY_NAME else []


def _cite(
    products: list[ExtractedLine], lines: dict[int, str], taken: set[int]
) -> set[int]:
    """Record each product's valid source lines, falling back to its name; return them."""
    cited: set[int] = set()
    for product in products:
        valid = [n for n in product.source_lines if n in lines]
        if not valid:
            valid = _cite_by_name(product, lines, taken | cited)
        product.source_lines = valid
        cited.update(valid)
    return cited


def _attach_details(
    open_lines: set[int], cited: set[int], lines: dict[int, str], layout: str
) -> set[int]:
    """Detail lines next to a cited product belong to it, not to the unaccounted set."""
    step = -1 if layout == "after" else 1
    attached = {
        n
        for n in open_lines
        if _is_detail(lines[n]) and n + step in cited and n + step not in open_lines
    }
    return open_lines - attached


def _suspect(other: OtherLine, lines: dict[int, str]) -> bool:
    """An `other` line with an amount on it may well be a product."""
    return other.kind == "other" and _has_amount(lines[other.line])


def _accounted_others(
    others: list[OtherLine], lines: dict[int, str], trust_other: bool = False
) -> set[int]:
    """Lines the answer listed as not products; a suspect one only when trusted."""
    return {
        o.line
        for o in others
        if o.line in lines and (trust_other or not _suspect(o, lines))
    }


def _raw_groups(
    still: list[int], lines: dict[int, str], layout: str
) -> list[list[int]]:
    """Group leftover lines so a name and its adjacent detail line make one row."""
    groups: list[list[int]] = []
    current: list[int] = []
    previous: int | None = None
    for n in still:
        text = lines[n]
        adjacent = bool(current) and previous == n - 1
        names = [m for m in current if not _is_detail(lines[m])]
        # A name line with no amount, last in its group, wraps onto the next line
        last = lines[current[-1]] if current else ""
        open_name = bool(last) and not _is_detail(last) and not _has_amount(last)
        if _is_detail(text):
            joins = adjacent and (layout == "after" or not names)
        else:
            joins = adjacent and (open_name or (layout == "before" and not names))
        if joins:
            current.append(n)
        else:
            current = [n]
            groups.append(current)
        previous = n
    return groups


def _raw_line(group: list[int], lines: dict[int, str]) -> ExtractedLine | None:
    """A leftover group with an amount on it, as printed, for the cook to decide."""
    texts = [lines[n] for n in group]
    if not any(_has_amount(text) for text in texts):
        return None
    names = [_strip_amounts(t) for t in texts if not _is_detail(t)]
    name = " ".join(part for part in names if part) or " ".join(
        part for part in (_strip_amounts(t) for t in texts) if part
    )
    return ExtractedLine(
        name=name or " ".join(texts),
        source_lines=group,
        recovered="raw_line",
    )


def receipt_arithmetic(
    products: list[ExtractedLine], others: list[OtherLine], total: float | None
) -> tuple[float | None, bool]:
    """Σ line totals plus signed discounts, deposits and fees; and whether it misses the total.

    Works for any currency and on the vision path. A detail line's unit price is never
    part of it: only a product's `p`, its line total, is summed.
    """
    prices = [p.price for p in products if p.price is not None]
    signed = [
        -abs(o.amount) if o.kind == "discount" else o.amount
        for o in others
        if o.kind in _SIGNED_KINDS and o.amount is not None
    ]
    if not prices:
        return None, False
    items_sum = round(sum(prices) + sum(signed), 2)
    if total is None:
        return items_sum, False
    return items_sum, abs(items_sum - total) > max(_SUM_TOLERANCE, abs(total) / 100)


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
    """The vision path has no text to account for; the arithmetic still applies."""
    items_sum, off = receipt_arithmetic(
        extraction.lines, extraction.other_lines, extraction.receipt_total
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


def _profile_evidence(
    extraction: ReceiptExtraction,
    numbered: list[tuple[int | None, str]],
    cited: set[int],
    receipt_id: str | None,
) -> tuple[str | None, set[int], int]:
    """(profile name, lines it says hold products no model product cites, how many)."""
    profile = profile_for(extraction.country, extraction.language)
    if profile is None:
        return None, set(), 0
    name = profile.language or profile.country
    try:
        found = profile.product_lines(numbered)
    except Exception as exc:  # a profile is evidence; it must never fail a receipt
        logger.warning(
            "Receipt profile failed, continuing without it",
            extra={"receipt_id": receipt_id, "profile": name, "error": repr(exc)},
        )
        return None, set(), 0
    missing = [p for p in found if not cited.intersection(p.line_numbers)]
    return name, {n for p in missing for n in p.line_numbers}, len(missing)


async def reconcile_text_read(
    text: str,
    extraction: ReceiptExtraction,
    categories: Sequence[CategoryOption],
    receipt_id: str | None = None,
) -> ReadOutcome:
    """Make sure every numbered line of a text receipt is accounted for (Q27).

    Model products the checks cannot place are kept as read; nothing is dropped.
    """
    numbered = number_receipt_lines(text)
    lines = {n: line for n, line in numbered if n is not None}
    first = list(extraction.lines)

    cited = _cite(first, lines, set())
    layout = _layout(first, lines)
    # When the line totals already add up to the printed total, an `other` line with an
    # amount on it is a loyalty or payment line, not a missing product: the money is
    # all accounted for. Measured on the K receipt, three such lines otherwise cost a
    # two-minute re-read that found nothing and three junk rows.
    first_sum, first_off = receipt_arithmetic(
        first, extraction.other_lines, extraction.receipt_total
    )
    adds_up = (
        first_sum is not None and extraction.receipt_total is not None and not first_off
    )
    accounted = cited | _accounted_others(extraction.other_lines, lines, adds_up)
    profile, profile_lines, profile_only = _profile_evidence(
        extraction, numbered, cited, receipt_id
    )
    # Only a line with an amount on it has to be accounted for; the model lists no other
    # non-product line, which keeps its answer short (a 49-line read ran past 180 s)
    priced = {n for n, line in lines.items() if _has_amount(line)}
    unaccounted = _attach_details(
        (priced - accounted) | profile_lines, cited, lines, layout
    )
    # An unpriced neighbour - a wrapped name, a name above its price line - goes to the
    # re-read with its partner, though on its own it needs no accounting
    context = unaccounted | {
        m
        for n in unaccounted
        for m in (n - 1, n + 1)
        if m in lines and m not in priced and m not in accounted
    }

    retry: ReceiptExtraction | None = None
    recovered: list[ExtractedLine] = []
    still = set(context)
    if any(_has_amount(lines[n]) for n in unaccounted):
        try:
            retry = await extract_unaccounted_lines(
                [(n, lines[n]) for n in sorted(context)], categories
            )
        except LLMExtractionError as exc:
            logger.warning(
                "Targeted re-read failed; listing unaccounted lines as printed",
                extra={"receipt_id": receipt_id, "error": str(exc)},
            )
    if retry is not None:
        for product in retry.lines:
            valid = [n for n in product.source_lines if n in still]
            if not valid and not product.source_lines:
                valid = _cite_by_name(product, {n: lines[n] for n in still}, set())
            if not valid:
                # it cites lines already accounted for: a second copy of a product
                continue
            product.source_lines = valid
            product.recovered = "model_retry"
            recovered.append(product)
            still -= set(valid)
        retry_cited = {n for p in recovered for n in p.source_lines}
        # A line the re-read, shown it on purpose and without the catalog, still lists
        # as not a product is accounted for; a profile's line needs a product, though
        still -= _accounted_others(retry.other_lines, lines, True) - profile_lines
        still = _attach_details(still, cited | retry_cited, lines, layout)

    raw_rows = [
        row
        for group in _raw_groups(sorted(still), lines, layout)
        if (row := _raw_line(group, lines)) is not None
    ]

    others = list(extraction.other_lines)
    if retry is not None:
        others += [o for o in retry.other_lines if o.line in context]
    items_sum, off = receipt_arithmetic(
        first + recovered, others, extraction.receipt_total
    )
    final = first + recovered + raw_rows
    extraction.lines = final
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
                "unaccounted_lines": len(unaccounted),
                "items_sum": items_sum,
                "receipt_total": extraction.receipt_total,
            },
        )
    return ReadOutcome(
        ocr_text=text,
        extraction=extraction,
        note=note,
        completeness=_completeness(
            text_lines=len(lines),
            model_lines=len(first),
            recovered_by_retry=len(recovered),
            recovered_raw_lines=len(raw_rows),
            invalid_entries=extraction.invalid_entries
            + (retry.invalid_entries if retry else 0),
            unaccounted_lines=len(unaccounted),
            items_sum=items_sum,
            receipt_total=extraction.receipt_total,
            profile=profile,
            profile_only_lines=profile_only,
        ),
        raw_completions=_raw(extraction, "raw_completion")
        | _raw(retry, "raw_completion_retry"),
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
        text_lines = len([n for n, _ in number_receipt_lines(text) if n is not None])
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
                    text_lines=text_lines, model_lines=0, unaccounted_lines=text_lines
                ),
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
                        text_lines=text_lines,
                        model_lines=0,
                        invalid_entries=extraction.invalid_entries,
                        unaccounted_lines=text_lines,
                    ),
                    raw_completions=_raw(extraction, "raw_completion"),
                )
        with timings.llm():
            return await reconcile_text_read(
                text, extraction, categories, receipt_id=str(receipt.id)
            )

    async def process_receipt(self, receipt: Receipt) -> ProcessingResult:
        """Process a receipt through the full pipeline and update the record."""
        row: Any = receipt  # Column-typed model: assign plain values
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
            row.processing_status = ReceiptStatus.FAILED
            row.error = error_msg
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
