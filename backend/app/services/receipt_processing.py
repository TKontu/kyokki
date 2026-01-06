"""Receipt processing service - orchestrates OCR, LLM extraction, and product matching.

Coordinates the full receipt processing pipeline:
1. OCR text extraction (pdfplumber or MinerU)
2. LLM product extraction (vLLM)
3. Fuzzy product matching (RapidFuzz)
4. Database updates
"""
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.services.ocr_service import extract_text_from_receipt
from app.services.llm_extractor import extract_products_from_receipt
from app.services.matching_service import MatchingService, MatchResult
from app.parsers.base import ReceiptExtraction
from app.core.logging import get_logger

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
    """Service for processing receipts through OCR → LLM → Matching pipeline."""

    def __init__(self, db: AsyncSession):
        """Initialize receipt processing service.

        Args:
            db: Database session for querying products and updating receipts.
        """
        self.db = db
        self.matching_service = MatchingService(db)

    async def process_receipt(self, receipt: Receipt) -> ProcessingResult:
        """Process a receipt through the full pipeline.

        Pipeline:
        1. Extract text via OCR (pdfplumber for PDF, MinerU for images)
        2. Extract products via LLM (vLLM with structured output)
        3. Match products to canonical product_master using fuzzy matching
        4. Update receipt record with results

        Args:
            receipt: Receipt database record to process.

        Returns:
            ProcessingResult with extraction results and any errors.
        """
        try:
            # Update status to processing
            receipt.processing_status = "processing"
            await self.db.commit()
            logger.info(f"Starting processing for receipt {receipt.id}")

            # Step 1: OCR text extraction
            logger.info(f"Extracting text from {receipt.image_path}")
            ocr_text = await extract_text_from_receipt(receipt.image_path)
            logger.info(f"OCR extracted {len(ocr_text)} characters")

            # Step 2: LLM product extraction
            logger.info("Extracting products with LLM")
            extraction = await extract_products_from_receipt(ocr_text)
            logger.info(
                f"LLM extracted {len(extraction.products)} products "
                f"(confidence: {extraction.confidence or 'N/A'})"
            )

            # Step 3: Fuzzy product matching
            matched_products = []
            for parsed_product in extraction.products:
                logger.debug(f"Matching product: {parsed_product.name}")
                match_result = await self.matching_service.match_product(
                    parsed_product.name
                )
                if match_result:
                    matched_products.append(match_result)
                    logger.info(
                        f"Matched '{parsed_product.name}' to "
                        f"'{match_result.product.canonical_name}' "
                        f"(confidence: {match_result.confidence.value}, "
                        f"score: {match_result.score:.1f})"
                    )
                else:
                    logger.warning(
                        f"No match found for '{parsed_product.name}'"
                    )

            # Step 4: Update receipt record
            receipt.processing_status = "completed"
            receipt.ocr_raw_text = ocr_text
            receipt.ocr_structured = {
                "store": extraction.store.model_dump() if extraction.store else None,
                "products": [p.to_dict() for p in extraction.products],
                "confidence": extraction.confidence,
            }
            receipt.items_extracted = len(extraction.products)
            receipt.items_matched = len(matched_products)

            # Update store chain if detected and not already set
            if extraction.store and extraction.store.chain and not receipt.store_chain:
                receipt.store_chain = extraction.store.chain

            await self.db.commit()
            await self.db.refresh(receipt)

            logger.info(
                f"Receipt {receipt.id} processing completed: "
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
            # Update status to failed
            receipt.processing_status = "failed"
            await self.db.commit()

            error_msg = f"Receipt processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return ProcessingResult(
                success=False,
                ocr_text=None,
                extraction=None,
                matched_products=[],
                error=error_msg,
            )
