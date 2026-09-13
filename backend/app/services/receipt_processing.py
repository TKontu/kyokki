"""Receipt processing service - orchestrates text or image extraction and product matching.

Pipeline:
1. Read the receipt: PDF text (pdfplumber) or image OCR (MinerU); when MinerU is unavailable or
   finds no text, the image is read directly by the vision-capable LLM.
2. Extract product lines, store, date and category suggestions with the LLM.
3. Fuzzy-match each line to product_master.
4. Store the structured result on the receipt.
"""

from dataclasses import dataclass

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.category import get_categories
from app.models.receipt import Receipt
from app.parsers.base import ReceiptExtraction
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

logger = get_logger(__name__)


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
        self, receipt: Receipt, categories: list[CategoryOption]
    ) -> tuple[str | None, ReceiptExtraction]:
        """Return (OCR text if any, extraction), choosing text or vision input."""
        path = str(receipt.image_path)

        if is_pdf(path):
            pdf_text = await extract_text_from_receipt(path)
            return pdf_text, await extract_from_text(pdf_text, categories)

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
            return text, await extract_from_text(text, categories)

        if text is not None:
            logger.warning(
                "OCR returned no text, reading the image with the vision model",
                extra={"receipt_id": str(receipt.id)},
            )
        image = await anyio.Path(path).read_bytes()
        return None, await extract_from_image(image, content_type_for(path), categories)

    async def process_receipt(self, receipt: Receipt) -> ProcessingResult:
        """Process a receipt through the full pipeline and update the record."""
        try:
            receipt.processing_status = "processing"
            await self.db.commit()
            logger.info(f"Starting processing for receipt {receipt.id}")
            await broadcast_receipt_status(receipt_id=receipt.id, status="processing")

            categories = [
                CategoryOption(id=str(c.id), name=str(c.display_name))
                for c in await get_categories(self.db)
            ]
            ocr_text, extraction = await self._read_receipt(receipt, categories)

            matched_products: list[MatchResult] = []
            for line in extraction.lines:
                match_result = await self.matching_service.match_product(line.name)
                if match_result:
                    matched_products.append(match_result)
                    logger.info(
                        f"Matched '{line.name}' to "
                        f"'{match_result.product.canonical_name}' "
                        f"(confidence: {match_result.confidence.value}, "
                        f"score: {match_result.score:.1f})"
                    )
                else:
                    logger.debug(f"No match found for '{line.name}'")

            receipt.processing_status = "completed"
            receipt.ocr_raw_text = ocr_text
            receipt.ocr_structured = extraction.model_dump(
                mode="json", include={"method", "store_chain", "purchase_date", "lines"}
            )
            receipt.items_extracted = len(extraction.lines)
            receipt.items_matched = len(matched_products)
            # Values the user entered at upload win over what was read from the receipt
            if extraction.store_chain and not receipt.store_chain:
                receipt.store_chain = extraction.store_chain
            if extraction.purchase_date and not receipt.purchase_date:
                receipt.purchase_date = extraction.purchase_date

            await self.db.commit()
            await self.db.refresh(receipt)

            await broadcast_receipt_status(
                receipt_id=receipt.id,
                status="completed",
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
            error_msg = f"Receipt processing failed: {str(e)}"

            receipt.processing_status = "failed"
            await self.db.commit()

            await broadcast_receipt_status(
                receipt_id=receipt.id, status="failed", error=error_msg
            )
            logger.error(error_msg, exc_info=True)

            return ProcessingResult(
                success=False,
                ocr_text=None,
                extraction=None,
                matched_products=[],
                error=error_msg,
            )
