"""Tests for receipt processing service (OCR or vision → LLM extraction → matching)."""

import logging
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import anyio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.schemas.receipt import ReceiptStatus
from app.services.llm_extractor import CategoryOption, LLMExtractionError
from app.services.ocr_service import OCRUnavailableError
from app.services.receipt_processing import ProcessingResult, ReceiptProcessingService

OCR = "app.services.receipt_processing.extract_text_from_receipt"
TEXT = "app.services.receipt_processing.extract_from_text"
VISION = "app.services.receipt_processing.extract_from_image"

# Text with no product lines: the heuristic fallback finds nothing to read
UNREADABLE_TEXT = "S-MARKET\n~~ blurred ~~\nYHTEENSÄ 7,48"

OCR_TEXT = """S-MARKET
VALIO WHOLE MILK 1L        2.49
ARLA BUTTER 500G           4.99
YHTEENSÄ                   7.48
"""


def _extraction(
    method: str = "text", lines: list[ExtractedLine] | None = None
) -> ReceiptExtraction:
    return ReceiptExtraction(
        method=method,
        store_chain="S-MARKET",
        purchase_date=date(2026, 1, 2),
        lines=lines
        if lines is not None
        else [
            ExtractedLine(name="Valio Whole Milk 1L", quantity=1, category="dairy"),
            ExtractedLine(name="Arla Butter 500g", quantity=1, category="dairy"),
        ],
    )


@pytest.fixture
async def sample_category(db_session: AsyncSession) -> Category:
    category = Category(
        id="dairy",
        display_name="Dairy & Eggs",
        icon="🥛",
        default_shelf_life_days=7,
        meal_contexts=["breakfast"],
        sort_order=1,
    )
    db_session.add(category)
    await db_session.commit()
    return category


@pytest.fixture
async def sample_product(
    db_session: AsyncSession, sample_category: Category
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Valio Whole Milk 1L",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
        default_quantity=Decimal("1000"),
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def _receipt(db_session: AsyncSession, image_path: str, **fields) -> Receipt:
    receipt = Receipt(
        id=uuid4(),
        image_path=image_path,
        processing_status="uploaded",
        items_extracted=0,
        items_matched=0,
        **fields,
    )
    db_session.add(receipt)
    await db_session.commit()
    return receipt


@pytest.fixture
async def pdf_receipt(db_session: AsyncSession, tmp_path) -> Receipt:
    path = tmp_path / "receipt.pdf"
    path.write_bytes(b"%PDF fake")
    return await _receipt(db_session, str(path))


@pytest.fixture
async def image_receipt(db_session: AsyncSession, tmp_path) -> Receipt:
    path = tmp_path / "receipt.png"
    path.write_bytes(b"\x89PNG fake image")
    return await _receipt(db_session, str(path))


@pytest.fixture
def service(db_session: AsyncSession) -> ReceiptProcessingService:
    return ReceiptProcessingService(db_session)


class TestInputSelection:
    async def test_pdf_uses_extracted_text(self, service, pdf_receipt, sample_category):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT) as ocr,
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()) as text,
            patch(VISION, new_callable=AsyncMock) as vision,
        ):
            result = await service.process_receipt(pdf_receipt)

        assert result.success is True
        ocr.assert_awaited_once_with(pdf_receipt.image_path)
        text.assert_awaited_once_with(
            OCR_TEXT, [CategoryOption(id="dairy", name="Dairy & Eggs")], []
        )
        vision.assert_not_awaited()

    async def test_image_with_ocr_text_uses_the_text_path(
        self, service, image_receipt, sample_category
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()) as text,
            patch(VISION, new_callable=AsyncMock) as vision,
        ):
            result = await service.process_receipt(image_receipt)

        assert result.success is True
        assert result.ocr_text == OCR_TEXT
        text.assert_awaited_once()
        vision.assert_not_awaited()

    async def test_image_falls_back_to_vision_when_ocr_is_unavailable(
        self, service, image_receipt, sample_category
    ):
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(TEXT, new_callable=AsyncMock) as text,
            patch(
                VISION, new_callable=AsyncMock, return_value=_extraction("vision")
            ) as vision,
        ):
            result = await service.process_receipt(image_receipt)

        assert result.success is True
        assert result.ocr_text is None
        text.assert_not_awaited()
        vision.assert_awaited_once_with(
            b"\x89PNG fake image",
            "image/png",
            [CategoryOption(id="dairy", name="Dairy & Eggs")],
            [],
        )

    async def test_image_falls_back_to_vision_when_ocr_returns_blank_text(
        self, service, image_receipt, sample_category
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value="  \n "),
            patch(TEXT, new_callable=AsyncMock) as text,
            patch(
                VISION, new_callable=AsyncMock, return_value=_extraction("vision")
            ) as vision,
        ):
            result = await service.process_receipt(image_receipt)

        assert result.success is True
        text.assert_not_awaited()
        vision.assert_awaited_once()


class TestPersistence:
    async def test_stores_structured_lines_method_store_and_date(
        self, service, image_receipt, sample_product, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(VISION, new_callable=AsyncMock, return_value=_extraction("vision")),
        ):
            result = await service.process_receipt(image_receipt)

        await db_session.refresh(image_receipt)
        assert image_receipt.processing_status == ReceiptStatus.COMPLETED
        assert image_receipt.ocr_raw_text is None
        structured = image_receipt.ocr_structured
        assert structured["method"] == "vision"
        assert structured["store_chain"] == "S-MARKET"
        assert structured["purchase_date"] == "2026-01-02"
        milk, butter = structured["lines"]
        assert milk == {
            "name": "Valio Whole Milk 1L",
            "generic_name": None,
            "quantity": 1.0,
            "weight_kg": None,
            "category": "dairy",
            "piece_grams": None,
            "shelf_life_days": None,
            "opened_shelf_life_days": None,
            "product_id": str(sample_product.id),
            "product_name": "Valio Whole Milk 1L",
            "product_storage_type": "refrigerator",
            "match_score": 100.0,
            "match_confidence": "exact",
            "match_source": "exact",
        }
        assert butter["product_id"] is None
        assert butter["product_name"] is None
        assert butter["match_score"] is None
        assert butter["match_confidence"] is None
        assert butter["match_source"] is None
        # The raw header text stays in ocr_structured; the receipt gets the chain key
        assert image_receipt.store_chain == "s-group"
        assert image_receipt.purchase_date == date(2026, 1, 2)
        assert image_receipt.items_extracted == 2
        assert image_receipt.items_matched == 1
        assert (
            result.matched_products[0].product.canonical_name == "Valio Whole Milk 1L"
        )

    async def test_weak_fuzzy_guesses_are_not_stored_as_matches(
        self, service, pdf_receipt, sample_category, db_session
    ):
        """Found in the R1b end-to-end run: CHEDDAR PUNAINEN scored 50 against PUNASIPULI and
        LIME 60. Only matches at or above FUZZY_MATCH_THRESHOLD may pre-select a product."""
        onion = ProductMaster(
            id=uuid4(),
            canonical_name="PUNASIPULI",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=14,
            unit_type="weight",
            default_unit="g",
        )
        db_session.add(onion)
        await db_session.commit()
        extraction = _extraction(
            lines=[
                ExtractedLine(name="CHEDDAR PUNAINEN", quantity=1, category="dairy"),
                ExtractedLine(
                    name="LIME", quantity=1, weight_kg=0.74, category="dairy"
                ),
                ExtractedLine(
                    name="PUNASIPULI", quantity=1, weight_kg=0.33, category="dairy"
                ),
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        cheddar, lime, red_onion = pdf_receipt.ocr_structured["lines"]
        assert cheddar["product_id"] is None
        assert lime["product_id"] is None
        assert red_onion["product_id"] == str(onion.id)
        assert pdf_receipt.items_matched == 1

    async def test_generic_name_is_stored_and_used_for_matching(
        self, service, pdf_receipt, sample_category, db_session
    ):
        beef = ProductMaster(
            id=uuid4(),
            canonical_name="Ground beef",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=3,
            unit_type="weight",
            default_unit="g",
        )
        db_session.add(beef)
        await db_session.commit()
        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="SNELLMAN NAUDAN JAUHELIHA 10%",
                    generic_name="Ground beef",
                    quantity=1,
                    category="dairy",
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction) as text,
        ):
            await service.process_receipt(pdf_receipt)

        # The catalog's names are offered to the model so it reuses them
        assert text.await_args.args[2] == ["Ground beef"]
        await db_session.refresh(pdf_receipt)
        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["generic_name"] == "Ground beef"
        assert line["product_id"] == str(beef.id)
        assert line["match_source"] == "exact"

    async def test_alias_match_is_stored_per_line(
        self, service, pdf_receipt, sample_product, db_session
    ):
        from app.models.store_product_alias import StoreProductAlias

        db_session.add(
            StoreProductAlias(
                product_master_id=sample_product.id,
                store_chain="s-group",
                receipt_name="VALIO TÄYSMAITO 1L",
                manually_verified=True,
            )
        )
        await db_session.commit()
        extraction = _extraction(
            lines=[
                ExtractedLine(name="VALIO TÄYSMAITO 1L", quantity=2, category="dairy")
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["product_id"] == str(sample_product.id)
        assert line["match_source"] == "alias"
        assert pdf_receipt.items_matched == 1

    async def test_keeps_store_and_date_the_user_already_entered(
        self, db_session, service, sample_category, tmp_path
    ):
        path = tmp_path / "receipt.pdf"
        path.write_bytes(b"%PDF fake")
        receipt = await _receipt(
            db_session,
            str(path),
            store_chain="K-Market",
            purchase_date=date(2026, 1, 1),
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()),
        ):
            await service.process_receipt(receipt)

        await db_session.refresh(receipt)
        assert receipt.store_chain == "K-Market"
        assert receipt.purchase_date == date(2026, 1, 1)
        assert receipt.ocr_raw_text == OCR_TEXT

    async def test_empty_extraction_still_completes(
        self, service, pdf_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=UNREADABLE_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction(lines=[])),
        ):
            result = await service.process_receipt(pdf_receipt)

        assert result.success is True
        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.processing_status == ReceiptStatus.COMPLETED
        assert pdf_receipt.items_extracted == 0
        assert pdf_receipt.items_matched == 0


class TestQueueFields:
    """MVP-R3: the worker has already claimed the receipt; failures are stored."""

    async def test_claimed_receipt_is_not_marked_processing_again(
        self, service, pdf_receipt, sample_category, db_session
    ):
        pdf_receipt.processing_status = ReceiptStatus.PROCESSING
        await db_session.commit()

        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()),
            patch(
                "app.services.receipt_processing.broadcast_receipt_status",
                new_callable=AsyncMock,
            ) as broadcast,
        ):
            await service.process_receipt(pdf_receipt)

        statuses = [call.kwargs["status"] for call in broadcast.await_args_list]
        assert statuses == [ReceiptStatus.COMPLETED]

    async def test_success_clears_a_previous_error(
        self, service, pdf_receipt, sample_category, db_session
    ):
        pdf_receipt.error = "LLM timed out"
        await db_session.commit()

        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.error is None
        assert pdf_receipt.processing_started_at is not None

    async def test_failure_stores_a_bounded_error(
        self, service, pdf_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=UNREADABLE_TEXT),
            patch(
                TEXT,
                new_callable=AsyncMock,
                side_effect=LLMExtractionError("timed out " + "x" * 2000),
            ),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.error.startswith("Receipt processing failed: timed out")
        assert len(pdf_receipt.error) <= 500


class TestFailures:
    async def test_extraction_error_marks_receipt_failed(
        self, service, pdf_receipt, sample_category, db_session
    ):
        """No readable product lines either: the heuristic cannot help and the receipt fails."""
        with (
            patch(OCR, new_callable=AsyncMock, return_value=UNREADABLE_TEXT),
            patch(
                TEXT,
                new_callable=AsyncMock,
                side_effect=LLMExtractionError("timed out"),
            ),
        ):
            result = await service.process_receipt(pdf_receipt)

        assert result.success is False
        assert "timed out" in (result.error or "")
        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.processing_status == ReceiptStatus.FAILED

    async def test_non_availability_ocr_error_does_not_fall_back(
        self, service, image_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=ValueError("corrupt file")),
            patch(VISION, new_callable=AsyncMock) as vision,
        ):
            result = await service.process_receipt(image_receipt)

        assert result.success is False
        vision.assert_not_awaited()
        await db_session.refresh(image_receipt)
        assert image_receipt.processing_status == ReceiptStatus.FAILED


class TestHeuristicFallback:
    """MVP-R3b: when the model fails or finds nothing, readable text still yields rows."""

    async def test_model_failure_on_text_falls_back_to_the_parser(
        self, service, pdf_receipt, sample_product, db_session
    ):
        from app.models.store_product_alias import StoreProductAlias

        db_session.add(
            StoreProductAlias(
                product_master_id=sample_product.id,
                store_chain="s-group",
                receipt_name="VALIO WHOLE MILK 1L",
                manually_verified=True,
            )
        )
        await db_session.commit()

        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(
                TEXT,
                new_callable=AsyncMock,
                side_effect=LLMExtractionError("LLM request failed: ConnectError"),
            ),
        ):
            result = await service.process_receipt(pdf_receipt)

        assert result.success is True
        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.processing_status == ReceiptStatus.COMPLETED
        assert pdf_receipt.error is None
        structured = pdf_receipt.ocr_structured
        assert structured["method"] == "heuristic"
        assert structured["fallback_reason"].startswith(
            "Model unavailable: LLM request failed: ConnectError"
        )
        milk, butter = structured["lines"]
        assert (milk["name"], milk["generic_name"], milk["category"]) == (
            "VALIO WHOLE MILK 1L",
            None,
            None,
        )
        assert milk["match_source"] == "alias"
        assert butter["name"] == "ARLA BUTTER 500G"
        assert pdf_receipt.store_chain == "s-group"
        assert (pdf_receipt.items_extracted, pdf_receipt.items_matched) == (2, 1)

    async def test_model_finding_nothing_falls_back_to_the_parser(
        self, service, pdf_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction(lines=[])),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.ocr_structured["method"] == "heuristic"
        assert (
            pdf_receipt.ocr_structured["fallback_reason"] == "Model found no products"
        )
        assert pdf_receipt.items_extracted == 2

    async def test_image_ocr_text_also_falls_back(
        self, service, image_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(
                TEXT,
                new_callable=AsyncMock,
                side_effect=LLMExtractionError("timed out"),
            ),
            patch(VISION, new_callable=AsyncMock) as vision,
        ):
            await service.process_receipt(image_receipt)

        vision.assert_not_awaited()
        await db_session.refresh(image_receipt)
        assert image_receipt.processing_status == ReceiptStatus.COMPLETED
        assert image_receipt.ocr_structured["method"] == "heuristic"

    async def test_vision_failure_has_no_text_to_parse(
        self, service, image_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(
                VISION,
                new_callable=AsyncMock,
                side_effect=LLMExtractionError("timed out"),
            ),
            patch("app.services.receipt_processing.parse_receipt_text") as parser,
        ):
            result = await service.process_receipt(image_receipt)

        assert result.success is False
        parser.assert_not_called()
        await db_session.refresh(image_receipt)
        assert image_receipt.processing_status == ReceiptStatus.FAILED

    async def test_model_success_records_no_fallback(
        self, service, pdf_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        assert pdf_receipt.ocr_structured["method"] == "text"
        assert "fallback_reason" not in pdf_receipt.ocr_structured


class TestProcessingResult:
    def test_holds_the_extraction(self):
        extraction = _extraction(lines=[])
        result = ProcessingResult(
            success=True,
            ocr_text=None,
            extraction=extraction,
            matched_products=[],
            error=None,
        )
        assert result.extraction is extraction


class TestTimingLog:
    """MVP-R4 is measured from the logs, so every read emits its own numbers."""

    @staticmethod
    def _read_line(caplog) -> object:
        lines = [r for r in caplog.records if hasattr(r, "total_seconds")]
        assert len(lines) == 1, [r.getMessage() for r in caplog.records]
        return lines[0]

    async def test_a_finished_receipt_logs_its_own_numbers(
        self, service, pdf_receipt, sample_category, caplog
    ):
        caplog.set_level(logging.INFO, logger="app.services.receipt_processing")

        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()),
            patch(VISION, new_callable=AsyncMock),
        ):
            result = await service.process_receipt(pdf_receipt)

        assert result.success is True
        line = self._read_line(caplog)
        assert line.receipt_id == str(pdf_receipt.id)
        assert line.method == "text"
        assert line.items_extracted == 2
        assert line.items_matched == 0
        # Both slow steps are timed separately: R4 records OCR time and LLM time per receipt
        assert line.ocr_seconds >= 0
        assert line.llm_seconds >= 0
        assert line.total_seconds >= line.ocr_seconds + line.llm_seconds

    async def test_the_vision_path_counts_as_model_time(
        self, service, image_receipt, sample_category, caplog
    ):
        caplog.set_level(logging.INFO, logger="app.services.receipt_processing")

        async def slow_vision(*args, **kwargs):
            # Timings are logged to a tenth of a second; a real vision call takes ~60
            await anyio.sleep(0.15)
            return _extraction(method="vision")

        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(TEXT, new_callable=AsyncMock),
            patch(VISION, new_callable=AsyncMock, side_effect=slow_vision),
        ):
            result = await service.process_receipt(image_receipt)

        assert result.success is True
        line = self._read_line(caplog)
        assert line.method == "vision"
        assert line.llm_seconds >= 0.1
        assert line.ocr_seconds == 0.0

    async def test_a_failed_receipt_still_reports_where_the_time_went(
        self, service, pdf_receipt, sample_category, caplog
    ):
        caplog.set_level(logging.INFO, logger="app.services.receipt_processing")

        with (
            patch(
                OCR, new_callable=AsyncMock, side_effect=RuntimeError("MinerU is down")
            ),
            patch(TEXT, new_callable=AsyncMock),
            patch(VISION, new_callable=AsyncMock),
        ):
            result = await service.process_receipt(pdf_receipt)

        assert result.success is False
        line = self._read_line(caplog)
        assert line.receipt_id == str(pdf_receipt.id)
        assert "MinerU is down" in line.error
        assert line.total_seconds >= 0


class TestPieceWeightOnStoredLines:
    """Q2: the catalog's own piece weight beats a fresh guess from the model."""

    async def test_a_matched_products_piece_weight_wins(
        self, service, pdf_receipt, sample_category, sample_product, db_session
    ):
        # The catalog already knows this product weighs 200 g a piece
        sample_product.avg_piece_grams = Decimal("200")
        await db_session.commit()

        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="Valio Whole Milk 1L",
                    quantity=1,
                    category="dairy",
                    piece_grams=125,
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["piece_grams"] == 200.0

    async def test_an_unmatched_line_keeps_the_models_guess(
        self, service, pdf_receipt, sample_category
    ):
        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="OMENA GOLDEN",
                    generic_name="Apple",
                    quantity=1,
                    weight_kg=1.072,
                    category="dairy",
                    piece_grams=125,
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["piece_grams"] == 125
