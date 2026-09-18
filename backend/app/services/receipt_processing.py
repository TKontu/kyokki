"""Receipt processing service - orchestrates text or image extraction and product matching.

Pipeline:
1. Read the receipt: PDF text (pdfplumber) or image OCR (MinerU); when MinerU is unavailable or
   finds no text, the image is read directly by the vision-capable LLM.
2. Extract product lines, store, date and category suggestions with the LLM.
3. Fuzzy-match each line to product_master.
4. Store the structured result on the receipt.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.category import get_categories
from app.models.receipt import Receipt
from app.parsers.base import ReceiptExtraction
from app.parsers.heuristic import parse_receipt_text
from app.schemas.receipt import ReceiptStatus
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.llm_extractor import (
    CategoryOption,
    LLMExtractionError,
    extract_from_image,
    extract_from_text,
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
    ) -> tuple[str | None, ReceiptExtraction, str | None]:
        """Return (OCR text if any, extraction, fallback reason), choosing text or vision input."""
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
        return None, extraction, None

    async def _read_text(
        self,
        receipt: Receipt,
        text: str,
        categories: list[CategoryOption],
        known_products: list[str],
        timings: ReadTimings,
    ) -> tuple[str, ReceiptExtraction, str | None]:
        """Extract with the model; if it fails or finds nothing, use the heuristic parser.

        The parser only helps when the text has product lines; otherwise the model's error
        stands and the receipt fails as before (MVP-R3b).
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
            return text, fallback, f"Model unavailable: {exc}"[:MAX_ERROR_CHARS]

        if not extraction.lines:
            fallback = parse_receipt_text(text)
            if fallback.lines:
                logger.warning(
                    "LLM found no products, using the heuristic parser",
                    extra={"receipt_id": str(receipt.id)},
                )
                return text, fallback, "Model found no products"
        return text, extraction, None

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
            ocr_text, extraction, fallback_reason = await self._read_receipt(
                receipt, categories, catalog, timings
            )

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
            }
            if fallback_reason:
                row.ocr_structured["fallback_reason"] = fallback_reason
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
