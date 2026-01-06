"""Tests for receipt processing service (OCR → LLM → Matching integration)."""
import pytest
from pathlib import Path
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.services.receipt_processing import ReceiptProcessingService, ProcessingResult
from app.models.receipt import Receipt
from app.models.product_master import ProductMaster
from app.models.category import Category
from app.parsers.base import ReceiptExtraction, ParsedProduct, StoreInfo
from sqlalchemy.ext.asyncio import AsyncSession


class TestReceiptProcessingService:
    """Test receipt processing service integration."""

    @pytest.fixture
    async def sample_category(self, db_session: AsyncSession) -> Category:
        """Create sample category for tests."""
        category = Category(
            id="dairy",
            display_name="Dairy",
            icon="🥛",
            default_shelf_life_days=7,
            meal_contexts=["breakfast"],
            sort_order=1,
        )
        db_session.add(category)
        await db_session.commit()
        await db_session.refresh(category)
        return category

    @pytest.fixture
    async def sample_product(
        self, db_session: AsyncSession, sample_category: Category
    ) -> ProductMaster:
        """Create sample product for matching tests."""
        product = ProductMaster(
            id=uuid4(),
            canonical_name="Valio Whole Milk 1L",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="ml",
            default_quantity=Decimal("1000"),
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)
        return product

    @pytest.fixture
    async def sample_receipt(self, db_session: AsyncSession) -> Receipt:
        """Create sample receipt for tests."""
        receipt = Receipt(
            id=uuid4(),
            store_chain="S-Market",
            image_path="/fake/path/receipt.pdf",
            processing_status="uploaded",
            items_extracted=0,
            items_matched=0,
        )
        db_session.add(receipt)
        await db_session.commit()
        await db_session.refresh(receipt)
        return receipt

    @pytest.fixture
    def processing_service(self, db_session: AsyncSession) -> ReceiptProcessingService:
        """Create processing service instance."""
        return ReceiptProcessingService(db_session)

    @pytest.fixture
    def mock_ocr_response(self) -> str:
        """Mock OCR text response."""
        return """S-MARKET
VALIO WHOLE MILK 1L        2.49
ARLA BUTTER 500G           4.99
TOTAL                      7.48
"""

    @pytest.fixture
    def mock_llm_extraction(self) -> ReceiptExtraction:
        """Mock LLM extraction result."""
        return ReceiptExtraction(
            store=StoreInfo(
                name="S-Market",
                chain="s-group",
                country="FI",
                language="fi",
                currency="EUR",
            ),
            products=[
                ParsedProduct(
                    name="Valio Whole Milk 1L",
                    quantity=1.0,
                    unit="pcs",
                    price=2.49,
                ),
                ParsedProduct(
                    name="Arla Butter 500g",
                    quantity=1.0,
                    unit="pcs",
                    price=4.99,
                ),
            ],
            confidence=0.95,
        )

    async def test_process_receipt_success(
        self,
        processing_service: ReceiptProcessingService,
        sample_receipt: Receipt,
        sample_product: ProductMaster,
        mock_ocr_response: str,
        mock_llm_extraction: ReceiptExtraction,
    ):
        """Test successful receipt processing pipeline."""
        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=mock_ocr_response,
        ) as mock_ocr:
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                return_value=mock_llm_extraction,
            ) as mock_llm:
                result = await processing_service.process_receipt(sample_receipt)

                # Verify OCR was called
                mock_ocr.assert_called_once_with(sample_receipt.image_path)

                # Verify LLM extraction was called
                mock_llm.assert_called_once_with(mock_ocr_response)

                # Verify result
                assert result.success is True
                assert result.ocr_text == mock_ocr_response
                assert result.extraction == mock_llm_extraction
                assert len(result.matched_products) >= 1
                # First product should match
                assert result.matched_products[0].product.canonical_name == "Valio Whole Milk 1L"

    async def test_process_receipt_updates_database(
        self,
        processing_service: ReceiptProcessingService,
        sample_receipt: Receipt,
        sample_product: ProductMaster,
        mock_ocr_response: str,
        mock_llm_extraction: ReceiptExtraction,
        db_session: AsyncSession,
    ):
        """Test that processing updates receipt in database."""
        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=mock_ocr_response,
        ):
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                return_value=mock_llm_extraction,
            ):
                await processing_service.process_receipt(sample_receipt)

                # Refresh receipt from database
                await db_session.refresh(sample_receipt)

                # Verify receipt was updated
                assert sample_receipt.processing_status == "completed"
                assert sample_receipt.ocr_raw_text == mock_ocr_response
                assert sample_receipt.ocr_structured is not None
                assert sample_receipt.items_extracted == 2
                assert sample_receipt.items_matched >= 1

    async def test_process_receipt_ocr_failure(
        self,
        processing_service: ReceiptProcessingService,
        sample_receipt: Receipt,
        db_session: AsyncSession,
    ):
        """Test handling of OCR failure."""
        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            side_effect=Exception("OCR service unavailable"),
        ):
            result = await processing_service.process_receipt(sample_receipt)

            assert result.success is False
            assert result.error is not None
            assert "OCR service unavailable" in result.error

            # Verify receipt status was updated
            await db_session.refresh(sample_receipt)
            assert sample_receipt.processing_status == "failed"

    async def test_process_receipt_llm_failure(
        self,
        processing_service: ReceiptProcessingService,
        sample_receipt: Receipt,
        mock_ocr_response: str,
        db_session: AsyncSession,
    ):
        """Test handling of LLM extraction failure."""
        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=mock_ocr_response,
        ):
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                side_effect=Exception("LLM service timeout"),
            ):
                result = await processing_service.process_receipt(sample_receipt)

                assert result.success is False
                assert result.error is not None
                assert "LLM service timeout" in result.error

                # Verify receipt status was updated
                await db_session.refresh(sample_receipt)
                assert sample_receipt.processing_status == "failed"

    async def test_process_receipt_no_products_extracted(
        self,
        processing_service: ReceiptProcessingService,
        sample_receipt: Receipt,
        mock_ocr_response: str,
        db_session: AsyncSession,
    ):
        """Test processing when no products are extracted."""
        empty_extraction = ReceiptExtraction(
            store=StoreInfo(),
            products=[],
            confidence=0.5,
        )

        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=mock_ocr_response,
        ):
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                return_value=empty_extraction,
            ):
                result = await processing_service.process_receipt(sample_receipt)

                # Should still succeed, just with no products
                assert result.success is True
                assert result.extraction == empty_extraction
                assert len(result.matched_products) == 0

                # Verify receipt status
                await db_session.refresh(sample_receipt)
                assert sample_receipt.processing_status == "completed"
                assert sample_receipt.items_extracted == 0
                assert sample_receipt.items_matched == 0

    async def test_process_receipt_partial_matching(
        self,
        processing_service: ReceiptProcessingService,
        sample_receipt: Receipt,
        sample_product: ProductMaster,  # Only one product in DB
        mock_ocr_response: str,
        mock_llm_extraction: ReceiptExtraction,  # But extraction has 2 products
        db_session: AsyncSession,
    ):
        """Test processing when only some products can be matched."""
        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=mock_ocr_response,
        ):
            with patch(
                "app.services.receipt_processing.extract_products_from_receipt",
                new_callable=AsyncMock,
                return_value=mock_llm_extraction,
            ):
                result = await processing_service.process_receipt(sample_receipt)

                assert result.success is True
                assert len(result.matched_products) >= 1  # At least one match
                assert len(result.matched_products) <= len(mock_llm_extraction.products)

                # Verify stats
                await db_session.refresh(sample_receipt)
                assert sample_receipt.items_extracted == 2
                # items_matched may be less than items_extracted
                assert sample_receipt.items_matched <= sample_receipt.items_extracted


class TestProcessingResult:
    """Test ProcessingResult data structure."""

    def test_processing_result_success(self):
        """Test creating successful processing result."""
        extraction = ReceiptExtraction(store=StoreInfo(), products=[])
        result = ProcessingResult(
            success=True,
            ocr_text="Sample text",
            extraction=extraction,
            matched_products=[],
            error=None,
        )

        assert result.success is True
        assert result.ocr_text == "Sample text"
        assert result.extraction == extraction
        assert result.matched_products == []
        assert result.error is None

    def test_processing_result_failure(self):
        """Test creating failed processing result."""
        result = ProcessingResult(
            success=False,
            ocr_text=None,
            extraction=None,
            matched_products=[],
            error="OCR failed",
        )

        assert result.success is False
        assert result.error == "OCR failed"
