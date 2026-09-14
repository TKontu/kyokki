"""Receipt processing service - orchestrates text or image extraction and product matching.

Pipeline:
1. Read the receipt: PDF text (pdfplumber) or image OCR (MinerU); when MinerU is unavailable or
   finds no text, the image is read directly by the vision-capable LLM.
2. Extract product lines, store, date and category suggestions with the LLM.
3. Fuzzy-match each line to product_master.
4. Store the structured result on the receipt.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.crud.category import get_categories
from app.models.receipt import Receipt
from app.parsers.base import ReceiptExtraction
from app.schemas.receipt import ReceiptStatus
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.llm_extractor import (
    CategoryOption,
    extract_from_image,
    extract_from_text,
)
from app.services.matching_service import MatchingService, MatchResult
from app.services.ocr_service import (
    OCRUnavailableError,
    content_type_for,
    extract_text_from_receipt,
    is_pdf,
)
from app.services.store_chain import normalize_store_chain

logger = get_logger(__name__)

MAX_ERROR_CHARS = 500  # stored on the receipt and shown to the user


@dataclass
class ProcessingResult:
    """Result of receipt processing pipeline."""

    success: bool
    ocr_text: str | None
    extraction: ReceiptExtraction | None
    matched_products: list[MatchResult]
    error: str | None = None


class ReceiptProcessingService:
    """Service for processing receipts through extraction → matching."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.matching_service = MatchingService(db)

    async def _read_receipt(
        self,
        receipt: Receipt,
        categories: list[CategoryOption],
        known_products: list[str],
    ) -> tuple[str | None, ReceiptExtraction]:
        """Return (OCR text if any, extraction), choosing text or vision input."""
        path = str(receipt.image_path)

        if is_pdf(path):
            pdf_text = await extract_text_from_receipt(path)
            return pdf_text, await extract_from_text(
                pdf_text, categories, known_products
            )

        text: str | None
        try:
            text = await extract_text_from_receipt(path)
        except OCRUnavailableError as exc:
            logger.warning(
                "OCR unavailable, reading the image with the vision model",
                extra={"receipt_id": str(receipt.id), "error": str(exc)},
            )
            text = None

        if text and text.strip():
            return text, await extract_from_text(text, categories, known_products)

        if text is not None:
            logger.warning(
                "OCR returned no text, reading the image with the vision model",
                extra={"receipt_id": str(receipt.id)},
            )
        image = await anyio.Path(path).read_bytes()
        return None, await extract_from_image(
            image, content_type_for(path), categories, known_products
        )

    async def process_receipt(self, receipt: Receipt) -> ProcessingResult:
        """Process a receipt through the full pipeline and update the record."""
        row: Any = receipt  # Column-typed model: assign plain values
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
            # Load the catalog first: its generic names are offered to the model for reuse
            await self.matching_service.prepare(None)
            ocr_text, extraction = await self._read_receipt(
                receipt, categories, self.matching_service.product_names
            )

            chain = normalize_store_chain(
                str(receipt.store_chain) if receipt.store_chain else None
            ) or normalize_store_chain(extraction.store_chain)

            matched_products: list[MatchResult] = []
            stored_lines = []
            for line in extraction.lines:
                # Only confident matches pre-select a product; weaker fuzzy guesses (the R1b
                # end-to-end run paired CHEDDAR PUNAINEN with PUNASIPULI at 50) stay unmatched
                match = self.matching_service.match_line(
                    line.name,
                    chain,
                    min_score=settings.FUZZY_MATCH_THRESHOLD,
                    generic_name=line.generic_name,
                )
                stored = line.model_dump(mode="json")
                stored.update(
                    product_id=str(match.product.id) if match else None,
                    product_name=match.product.canonical_name if match else None,
                    product_storage_type=match.product.storage_type if match else None,
                    match_score=round(match.score, 1) if match else None,
                    match_confidence=match.confidence.value if match else None,
                    match_source=match.source if match else None,
                )
                stored_lines.append(stored)
                if match:
                    matched_products.append(match)

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
            row.items_extracted = len(extraction.lines)
            row.items_matched = len(matched_products)
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
            logger.info(
                f"Receipt {receipt.id} processing completed via {extraction.method}: "
                f"{receipt.items_extracted} extracted, {receipt.items_matched} matched"
            )

            return ProcessingResult(
                success=True,
                ocr_text=ocr_text,
                extraction=extraction,
                matched_products=matched_products,
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
            logger.error(error_msg, exc_info=True)

            return ProcessingResult(
                success=False,
                ocr_text=None,
                extraction=None,
                matched_products=[],
                error=error_msg,
            )
