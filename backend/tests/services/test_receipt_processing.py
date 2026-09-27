"""Tests for receipt processing service (OCR or vision → LLM extraction → matching)."""

import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.non_food_name import NonFoodName
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.parsers.base import ExtractedLine, OtherLine, ReceiptExtraction
from app.parsers.profiles import FinnishProfile
from app.schemas.receipt import ReceiptStatus
from app.services import receipt_processing
from app.services.llm_extractor import (
    CategoryOption,
    LLMExtractionError,
    number_receipt_lines,
)
from app.services.ocr_service import OCRUnavailableError
from app.services.receipt_processing import (
    ProcessingResult,
    ReceiptProcessingService,
    receipt_arithmetic,
    reconcile_text_read,
)


class _FakeClock:
    """Stands in for the ``time`` module so a test can advance it by hand."""

    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value


OCR = "app.services.receipt_processing.extract_text_from_receipt"
TEXT = "app.services.receipt_processing.extract_from_text"
VISION = "app.services.receipt_processing.extract_from_image"
RETRY = "app.services.receipt_processing.extract_unaccounted_lines"


@pytest.fixture(autouse=True)
def no_unplanned_re_read():
    """The targeted re-read (Q27) runs only when a test sets it up.

    Left unpatched it would call the configured gateway; a test that triggers it by
    accident fails instead.
    """
    with patch(
        RETRY,
        new_callable=AsyncMock,
        side_effect=AssertionError("unexpected targeted re-read"),
    ) as retry:
        yield retry


# Text with no product lines: the heuristic fallback finds nothing to read
UNREADABLE_TEXT = "S-MARKET\n~~ blurred ~~\nYHTEENSÄ 7,48"

OCR_TEXT = """S-MARKET
VALIO WHOLE MILK 1L        2.49
ARLA BUTTER 500G           4.99
YHTEENSÄ                   7.48
"""


def _extraction(
    method: str = "text",
    lines: list[ExtractedLine] | None = None,
    total_line: int = 4,
) -> ReceiptExtraction:
    """The model's answer; by default for OCR_TEXT, whose line 4 is the total (Q27)."""
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
        other_lines=[OtherLine(line=total_line, kind="total", amount=7.48)],
    )


def _text_for(extraction: ReceiptExtraction) -> str:
    """Receipt text holding exactly the stubbed lines.

    Since Q27 every priced line of the text must be accounted for, so a stub that reads
    one product from a two-product text would (rightly) trigger a re-read. Tests about
    something else print the receipt their stub describes.
    """
    body = "\n".join(f"{line.name} 1,00" for line in extraction.lines)
    return f"S-MARKET\n{body}\n"


@pytest.fixture
async def sample_category(db_session: AsyncSession) -> Category:
    category = Category(
        id="dairy",
        display_name="Dairy & Eggs",
        icon="🥛",
        default_shelf_life_days=7,
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
        # line_id is a fresh uuid per read, so it is checked separately below.
        assert {k: v for k, v in milk.items() if k != "line_id"} == {
            "name": "Valio Whole Milk 1L",
            "generic_name": None,
            "quantity": 1.0,
            "weight_kg": None,
            "category": "dairy",
            "piece_grams": None,
            "shelf_life_days": None,
            "opened_shelf_life_days": None,
            "non_food": False,
            # Q27: the lines it was read from, its printed line total, and whether the
            # first read missed it (a stub without line numbers cites none)
            "source_lines": [],
            "price": None,
            "recovered": None,
            "product_id": str(sample_product.id),
            "product_name": "Valio Whole Milk 1L",
            "product_storage_type": "refrigerator",
            # No score decides anything any more (H13); the fields stay only so older
            # clients keep parsing, and H15 drops them from the review row.
            "match_score": None,
            "match_confidence": None,
            "match_source": "name",
            # How the line came to point at a product. A known catalog name is a key,
            # so it is verified - the review row may call it "known".
            "resolution": {
                "product_id": str(sample_product.id),
                "source": "name",
                "verified": True,
                "candidates": [],
            },
        }
        assert UUID(milk["line_id"])
        assert butter["product_id"] is None
        assert butter["product_name"] is None
        assert butter["match_score"] is None
        assert butter["match_confidence"] is None
        assert butter["match_source"] is None
        # Unresolved, but the shortlist it was offered is recorded: that is what the
        # model would have chosen from, and what H15 shows when the cook opens Change.
        assert butter["resolution"]["product_id"] is None
        assert butter["resolution"]["source"] == "none"
        assert butter["resolution"]["verified"] is False
        assert [c["name"] for c in butter["resolution"]["candidates"]] == [
            "Valio Whole Milk 1L"
        ]
        assert UUID(butter["line_id"]) != UUID(milk["line_id"])
        # The raw header text stays in ocr_structured; the receipt gets the chain key
        assert image_receipt.store_chain == "s-group"
        assert image_receipt.purchase_date == date(2026, 1, 2)
        assert image_receipt.items_extracted == 2
        assert image_receipt.items_matched == 1
        resolved = [r for r in result.resolutions.values() if r.product is not None]
        assert [str(r.product.canonical_name) for r in resolved] == [
            "Valio Whole Milk 1L"
        ]
        assert [r.source for r in resolved] == ["name"]

    async def test_a_re_read_keeps_each_line_its_identity(
        self, service, image_receipt, sample_product, db_session
    ):
        """The point of line_id: a re-read builds a fresh list of lines, and anything
        keyed to the old one - the cook's edits, non-food memory - would otherwise be
        pointing at rows that no longer exist (H12)."""
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(VISION, new_callable=AsyncMock, return_value=_extraction("vision")),
        ):
            await service.process_receipt(image_receipt)
        await db_session.refresh(image_receipt)
        first = [line["line_id"] for line in image_receipt.ocr_structured["lines"]]

        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(VISION, new_callable=AsyncMock, return_value=_extraction("vision")),
        ):
            await service.process_receipt(image_receipt)
        await db_session.refresh(image_receipt)
        second = [line["line_id"] for line in image_receipt.ocr_structured["lines"]]

        assert second == first

    async def test_a_line_the_re_read_did_not_find_gives_up_its_id(
        self, service, image_receipt, sample_product, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(VISION, new_callable=AsyncMock, return_value=_extraction("vision")),
        ):
            await service.process_receipt(image_receipt)
        await db_session.refresh(image_receipt)
        milk_id = image_receipt.ocr_structured["lines"][0]["line_id"]

        # The second read finds the milk again but reads the other line differently.
        rewritten = _extraction(
            "vision",
            [
                ExtractedLine(name="Valio Whole Milk 1L", quantity=1, category="dairy"),
                ExtractedLine(name="ARLA VOI 500G", quantity=1, category="dairy"),
            ],
        )
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(VISION, new_callable=AsyncMock, return_value=rewritten),
        ):
            await service.process_receipt(image_receipt)
        await db_session.refresh(image_receipt)
        milk, butter = image_receipt.ocr_structured["lines"]

        assert milk["line_id"] == milk_id
        assert butter["line_id"] != milk_id

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
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
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
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction) as text,
        ):
            await service.process_receipt(pdf_receipt)

        # The catalog's names are offered to the model so it reuses them
        assert text.await_args.args[2] == ["Ground beef"]
        await db_session.refresh(pdf_receipt)
        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["generic_name"] == "Ground beef"
        assert line["product_id"] == str(beef.id)
        # `exact` in the old vocabulary; a known catalog name is now `name` (H12/H13)
        assert line["match_source"] == "name"

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
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
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
        empty = _extraction(lines=[], total_line=3)
        with (
            patch(OCR, new_callable=AsyncMock, return_value=UNREADABLE_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=empty),
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
            resolutions={},
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
        self, service, image_receipt, sample_category, caplog, monkeypatch
    ):
        caplog.set_level(logging.INFO, logger="app.services.receipt_processing")

        # A fake clock instead of a real sleep. receipt_processing reads the elapsed
        # time from time.monotonic() and nothing else off the time module, so the
        # call can advance the clock rather than the test waiting for it.
        clock = _FakeClock()
        monkeypatch.setattr(receipt_processing, "time", clock)

        async def slow_vision(*args, **kwargs):
            # Timings are logged to a tenth of a second; a real vision call takes ~60
            clock.value += 0.15
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
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
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
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["piece_grams"] == 125


class TestPackWeightOnStoredLines:
    """Q8: what one pack weighs, from the catalog or from the printed name.

    Never from the model. Offered a `pk` contract field it answered on 1 line of 49 and
    dragged `sl` and `os` down with it (docs/vLLM_MANUAL_TEST.md), so the two sources
    here are the only ones - plus the cook, in the product editor.
    """

    async def test_a_matched_products_pack_weight_wins(
        self, service, pdf_receipt, sample_category, sample_product, db_session
    ):
        # The catalog already knows a pack of this is 500 g
        sample_product.pack_grams = Decimal("500")
        await db_session.commit()

        extraction = _extraction(
            lines=[
                ExtractedLine(name="Valio Whole Milk 1L", quantity=1, category="dairy")
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["pack_grams"] == 500.0

    async def test_an_unmatched_line_takes_the_size_the_shop_printed(
        self, service, pdf_receipt, sample_category
    ):
        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="SIKA-NAUTAJAUHELIHA 400G",
                    generic_name="Ground beef",
                    quantity=1,
                    category="dairy",
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["pack_grams"] == 400.0

    async def test_a_line_with_no_printed_size_stores_none(
        self, service, pdf_receipt, sample_category
    ):
        """Mince usually prints no weight at all - that is the whole of Q8's problem."""
        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="SIKA-NAUTAJAUHELIHA 23%",
                    generic_name="Ground beef",
                    quantity=1,
                    category="dairy",
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert "pack_grams" not in line


class TestNonFoodLines:
    """Q1: household lines should stop being offered as food."""

    async def test_the_model_saying_household_marks_the_line(
        self, service, pdf_receipt, sample_category
    ):
        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="SIENILIINA", generic_name="Cleaning cloth", non_food=True
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["non_food"] is True

    async def test_a_remembered_name_marks_it_even_when_the_model_forgets(
        self, service, pdf_receipt, sample_category, db_session
    ):
        """The whole point of remembering: the model does not have to be right every week."""
        db_session.add(
            NonFoodName(
                store_chain="s-group", receipt_name="KOMPOSTOINTIPUSSI", times_seen=1
            )
        )
        await db_session.commit()

        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="Kompostointipussi", generic_name="Compost bag", non_food=False
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["non_food"] is True

    async def test_an_ordinary_food_line_is_untouched(
        self, service, pdf_receipt, sample_category
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_extraction()),
            patch(VISION, new_callable=AsyncMock),
        ):
            await service.process_receipt(pdf_receipt)

        assert all(not line["non_food"] for line in pdf_receipt.ocr_structured["lines"])


# --- Completeness (Q27) --------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures" / "receipts"
K_TEXT = (FIXTURES / "k_citymarket_sello.txt").read_text(encoding="utf-8")
HR_TEXT = (FIXTURES / "konzum_hr_synthetic.txt").read_text(encoding="utf-8")
DE_TEXT = (FIXTURES / "rewe_de_synthetic.txt").read_text(encoding="utf-8")
CATEGORY_OPTIONS = [CategoryOption(id="produce", name="Vegetables")]


def _prompt_lines(text: str) -> dict[int, str]:
    return {n: line for n, line in number_receipt_lines(text) if n is not None}


def _at(text: str, *starts: str) -> list[int]:
    """The prompt numbers of the lines beginning with each of ``starts``."""
    lines = _prompt_lines(text)
    return [next(n for n, line in lines.items() if line.startswith(s)) for s in starts]


def _line(text: str, name: str, *starts: str, **fields) -> ExtractedLine:
    """A product as the model answers it, citing the lines it was read from."""
    return ExtractedLine(name=name, source_lines=_at(text, *starts), **fields)


def _answer(
    text: str,
    products: list[ExtractedLine],
    kinds: dict[str, tuple[str, float | None]] | None = None,
    missed: tuple[str, ...] = (),
    **fields,
) -> ReceiptExtraction:
    """The model's answer: its products, and every other line in `x`.

    ``kinds`` names a line's kind and amount by how it begins (default: header). Lines
    beginning with one of ``missed`` are in neither: the model left them out.
    """
    cited = {n for p in products for n in p.source_lines}
    others = []
    for n, line in _prompt_lines(text).items():
        if n in cited or line.startswith(missed or ("\0",)):
            continue
        kind, amount = next(
            (v for start, v in (kinds or {}).items() if line.startswith(start)),
            ("header", None),
        )
        others.append(OtherLine(line=n, kind=kind, amount=amount))
    return ReceiptExtraction(
        method="text", lines=products, other_lines=others, **fields
    )


K_FOOTER = {
    "PLUSSAA": ("subtotal", 73.07),
    "Käyttötavaraostokset": ("subtotal", 8.37),
    "Ruokaostokset": ("subtotal", 64.7),
    "Credit/Veloitus": ("payment", 73.07),
    "2 13,50%": ("tax", 8.1),
    "3 25,50%": ("tax", 1.01),
}


def _k_six() -> list[ExtractedLine]:
    """The six products the model really returned for the K-Citymarket receipt."""
    t = K_TEXT
    return [
        _line(
            t,
            "Kiinteä Peruna pesty Jazzy",
            "Kiinteä",
            "0,596",
            generic_name="Potato",
            category="produce",
            weight_kg=0.596,
            price=0.59,
        ),
        _line(
            t,
            "Pirkka miniluumutomaatti 250g",
            "Pirkka mini",
            generic_name="Cherry tomato",
            category="produce",
            price=2.29,
        ),
        _line(
            t,
            "Snäxi minipaprika mix 200g",
            "Snäxi",
            generic_name="Pepper",
            category="produce",
            price=1.99,
        ),
        _line(
            t,
            "Helmitomaatti pikari 200g",
            "Helmitomaatti",
            generic_name="Cherry tomato",
            category="produce",
            price=3.99,
        ),
        _line(
            t,
            "Hapankaali 400g Rasilainen",
            "Hapankaali",
            "2 KPL 2,99",
            generic_name="Sauerkraut",
            category="pantry",
            quantity=2,
            price=5.98,
        ),
        _line(
            t,
            "Baba punajuuri hummus 225g",
            "Baba",
            "2 KPL 3,69",
            generic_name="Hummus",
            category="pantry",
            quantity=2,
            price=7.38,
        ),
    ]


def _k_nine() -> list[ExtractedLine]:
    """The nine products the first read left out, as a targeted re-read returns them."""
    t = K_TEXT
    return [
        _line(
            t,
            "Bakerika suol suklaahipkeksita",
            "Bakerika",
            generic_name="Cookie",
            price=4.27,
        ),
        _line(
            t,
            "Pingviini jäätelö 1l suklaa la",
            "Pingviini",
            generic_name="Ice cream",
            price=2.99,
        ),
        _line(
            t,
            "Pirkka rypäle tumma 500g",
            "Pirkka rypäle",
            generic_name="Grape",
            price=2.79,
        ),
        _line(
            t,
            "Naudan Entrecote Palana",
            "Naudan",
            "0,913",
            generic_name="Entrecote",
            weight_kg=0.913,
            price=22.83,
        ),
        _line(t, "Nikulan vapaa L15 1020g", "Nikulan", generic_name="Egg", price=4.59),
        _line(
            t,
            "Palsternakka",
            "Palsternakka",
            "0,523",
            generic_name="Parsnip",
            weight_kg=0.523,
            price=1.04,
        ),
        _line(
            t,
            "Palmolive Vaahtosaippua 250ml",
            "Palmolive",
            "2 KPL 2,49",
            generic_name="Soap",
            quantity=2,
            non_food=True,
            price=4.98,
        ),
        _line(
            t,
            "Parsakaali 250g luomu",
            "Parsakaali",
            generic_name="Broccoli",
            price=3.97,
        ),
        _line(
            t,
            "Pirkka tamponi 32kpl sup",
            "Pirkka tamponi",
            generic_name="Tampon",
            non_food=True,
            price=3.39,
        ),
    ]


K_MISSED = (
    "Bakerika",
    "Pingviini",
    "Pirkka rypäle",
    "Naudan",
    "0,913",
    "Nikulan",
    "Palsternakka",
    "0,523",
    "Palmolive",
    "2 KPL 2,49",
    "Parsakaali",
    "Pirkka tamponi",
)


def _k_first_read(**fields) -> ReceiptExtraction:
    return _answer(
        K_TEXT,
        _k_six(),
        K_FOOTER,
        missed=K_MISSED,
        language="fi",
        country="FI",
        raw_completion='{"p": ["six products"]}',
        **fields,
    )


def _retry_answer(lines: list[ExtractedLine]) -> ReceiptExtraction:
    return ReceiptExtraction(
        method="text", lines=lines, raw_completion='{"p": ["the rest"]}'
    )


class TestKCitymarketCompleteness:
    """Q27: the model read 6 of the receipt's 15 products and nothing said so."""

    async def test_the_nine_missed_lines_are_re_read_in_one_call(
        self, no_unplanned_re_read
    ):
        retry = no_unplanned_re_read
        retry.side_effect = None
        retry.return_value = _retry_answer(_k_nine())

        outcome = await reconcile_text_read(K_TEXT, _k_first_read(), CATEGORY_OPTIONS)

        retry.assert_awaited_once()
        asked = retry.await_args.args[0]
        # a name line and its weight line go to the re-read together
        assert (10, "Naudan Entrecote Palana 22,83") in asked
        assert (11, "0,913 KG 25,00 €/KG") in asked
        assert [n for n, _ in asked] == [7, 8, 9, 10, 11, 16, 17, 18, 19, 20, 21, 22]
        # line 6 "K004 M000000/0000 11.49 26.9.2026" is priced-looking but in x
        # and the catalog is not offered to it
        assert retry.await_args.args[1] == CATEGORY_OPTIONS
        lines = outcome.extraction.lines
        assert len(lines) == 15
        assert [line.recovered for line in lines].count("model_retry") == 9
        assert all(line.recovered is None for line in lines[:6])
        assert outcome.completeness == {
            # every non-blank line, the total and VAT lines included
            "text_lines": 53,
            "model_lines": 6,
            "recovered_by_retry": 9,
            "recovered_raw_lines": 0,
            "invalid_entries": 0,
            "unaccounted_lines": 12,
            "items_sum": 73.07,
            # the total line is left out of the prompt on Finnish receipts
            "receipt_total": None,
            "profile": "fi",
            "profile_only_lines": 9,
        }
        assert outcome.note == (
            "9 of 15 lines were not read by the model and were recovered"
        )
        assert outcome.raw_completions == {
            "raw_completion": '{"p": ["six products"]}',
            "raw_completion_retry": '{"p": ["the rest"]}',
        }

    async def test_when_the_re_read_fails_the_printed_lines_are_listed(
        self, no_unplanned_re_read
    ):
        no_unplanned_re_read.side_effect = LLMExtractionError("gateway down")

        outcome = await reconcile_text_read(K_TEXT, _k_first_read(), CATEGORY_OPTIONS)

        rows = [line for line in outcome.extraction.lines if line.recovered]
        assert [row.name for row in rows] == [
            "Bakerika suol suklaahipkeksita",
            "Pingviini jäätelö 1l suklaa la",
            "Pirkka rypäle tumma 500g",
            "Naudan Entrecote Palana",
            "Nikulan vapaa L15 1020g",
            "Palsternakka",
            "Palmolive Vaahtosaippua 250ml",
            "Parsakaali 250g luomu",
            "Pirkka tamponi 32kpl sup",
        ]
        assert all(row.recovered == "raw_line" for row in rows)
        assert all(row.generic_name is None and row.category is None for row in rows)
        # the weight line is part of its product's row, not a row of its own
        entrecote = rows[3]
        assert entrecote.source_lines == [10, 11]
        assert len(outcome.extraction.lines) == 15
        assert outcome.completeness["recovered_raw_lines"] == 9
        assert outcome.completeness["recovered_by_retry"] == 0
        assert outcome.raw_completions == {"raw_completion": '{"p": ["six products"]}'}

    async def test_a_full_answer_makes_no_extra_call(self, no_unplanned_re_read):
        full = _answer(
            K_TEXT, _k_six() + _k_nine(), K_FOOTER, language="fi", country="FI"
        )

        outcome = await reconcile_text_read(K_TEXT, full, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert len(outcome.extraction.lines) == 15
        assert all(line.recovered is None for line in outcome.extraction.lines)
        assert outcome.note is None
        assert outcome.completeness["recovered_by_retry"] == 0
        assert outcome.completeness["recovered_raw_lines"] == 0
        assert outcome.completeness["unaccounted_lines"] == 0
        assert outcome.completeness["profile_only_lines"] == 0

    async def test_the_profile_catches_lines_the_model_called_non_products(
        self, no_unplanned_re_read
    ):
        """The model may list a product line in x; only the `fi` profile then knows."""
        hidden = _answer(
            K_TEXT, _k_six(), K_FOOTER, language="fi", country="FI"
        )  # every missed line listed as a header
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer(_k_nine())

        outcome = await reconcile_text_read(K_TEXT, hidden, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_awaited_once()
        assert len(outcome.extraction.lines) == 15
        assert outcome.completeness["profile"] == "fi"
        assert outcome.completeness["profile_only_lines"] == 9

    async def test_without_a_detected_country_or_language_no_profile_runs(
        self, no_unplanned_re_read
    ):
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer(_k_nine())
        first = _k_first_read()
        first.language = first.country = None

        outcome = await reconcile_text_read(K_TEXT, first, CATEGORY_OPTIONS)

        # the core's own accounting still finds all nine
        assert len(outcome.extraction.lines) == 15
        assert outcome.completeness["profile"] is None
        assert outcome.completeness["profile_only_lines"] == 0

    async def test_a_failing_profile_never_fails_the_receipt(
        self, no_unplanned_re_read, caplog
    ):
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer(_k_nine())

        with patch.object(
            FinnishProfile, "product_lines", side_effect=RuntimeError("bad grammar")
        ):
            outcome = await reconcile_text_read(
                K_TEXT, _k_first_read(), CATEGORY_OPTIONS
            )

        assert len(outcome.extraction.lines) == 15
        assert outcome.completeness["profile"] is None
        assert any("profile failed" in r.getMessage() for r in caplog.records)


def _hr_all() -> list[ExtractedLine]:
    t = HR_TEXT
    return [
        # a count line after the name
        _line(
            t, "Mlijeko svježe 2,8% m.m. 1l", "Mlijeko", "2 kom", quantity=2, price=2.58
        ),
        _line(t, "Kruh bijeli 500g", "Kruh", price=1.49),
        # a weight line after the name
        _line(
            t, "Jabuke Zlatni delišes", "Jabuke", "0,845", weight_kg=0.845, price=1.68
        ),
        # a name wrapped over two lines
        _line(
            t,
            "Čokolada mliječna s lješnjacima i grožđicama 100g",
            "Čokolada",
            "i grožđicama",
            price=2.19,
        ),
        _line(t, "Rajčica", "Rajčica", "0,512", weight_kg=0.512, price=1.27),
        _line(t, "Jogurt tekući 1l", "Jogurt", price=1.15),
        _line(t, "Sir Gauda narezani 150g", "Sir", price=2.39),
        _line(t, "Deterdžent za suđe 500ml", "Deterdžent", non_food=True, price=1.99),
    ]


HR_KINDS = {
    "UKUPNO": ("total", 14.74),
    "PDV": ("tax", None),
    "Gotovina": ("payment", 20.0),
    "Povrat": ("payment", -5.26),
}


class TestCroatianReceipt:
    """Amendment 1: a receipt from anywhere, with no profile, through the core alone."""

    async def test_multi_line_items_read_in_full_need_nothing_more(
        self, no_unplanned_re_read
    ):
        answer = _answer(
            HR_TEXT,
            _hr_all(),
            HR_KINDS,
            language="hr",
            country="HR",
            receipt_total=14.74,
        )

        outcome = await reconcile_text_read(HR_TEXT, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert len(outcome.extraction.lines) == 8
        assert outcome.note is None
        assert outcome.completeness["items_sum"] == 14.74
        assert outcome.completeness["receipt_total"] == 14.74
        assert outcome.completeness["profile"] is None

    async def test_a_missed_multi_line_item_goes_to_the_re_read_whole(
        self, no_unplanned_re_read
    ):
        read = [p for p in _hr_all() if p.name not in ("Jabuke Zlatni delišes",)]
        answer = _answer(
            HR_TEXT, read, HR_KINDS, missed=("Jabuke", "0,845"), receipt_total=14.74
        )
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer(
            [
                _line(
                    HR_TEXT,
                    "Jabuke Zlatni delišes",
                    "Jabuke",
                    "0,845",
                    weight_kg=0.845,
                    price=1.68,
                )
            ]
        )

        outcome = await reconcile_text_read(HR_TEXT, answer, CATEGORY_OPTIONS)

        assert no_unplanned_re_read.await_args.args[0] == [
            (10, "Jabuke Zlatni delišes"),
            (11, "0,845 kg x 1,99               1,68"),
        ]
        (apples,) = [p for p in outcome.extraction.lines if p.recovered]
        assert (apples.recovered, apples.weight_kg) == ("model_retry", 0.845)
        # with the re-read's line total the sums agree again
        assert outcome.completeness["items_sum"] == 14.74
        assert "add up" not in (outcome.note or "")

    async def test_when_nothing_recovers_it_the_arithmetic_flags_the_gap(
        self, no_unplanned_re_read
    ):
        read = [p for p in _hr_all() if not p.name.startswith(("Jabuke", "Čokolada"))]
        answer = _answer(
            HR_TEXT,
            read,
            HR_KINDS,
            missed=("Jabuke", "0,845", "Čokolada", "i grožđicama"),
            receipt_total=14.74,
        )
        no_unplanned_re_read.side_effect = LLMExtractionError("gateway down")

        outcome = await reconcile_text_read(HR_TEXT, answer, CATEGORY_OPTIONS)

        asked = [n for n, _ in no_unplanned_re_read.await_args.args[0]]
        assert asked == [10, 11, 12, 13]
        rows = [p for p in outcome.extraction.lines if p.recovered == "raw_line"]
        # one row per item: the weight line and the wrapped half join their names
        assert [(row.name, row.source_lines) for row in rows] == [
            ("Jabuke Zlatni delišes", [10, 11]),
            ("Čokolada mliječna s lješnjacima i grožđicama 100g", [12, 13]),
        ]
        assert outcome.completeness["items_sum"] == 10.87
        assert "Line totals add up to 10.87 but the receipt total is 14.74" in (
            outcome.note
        )


def _de_all() -> list[ExtractedLine]:
    t = DE_TEXT
    return [
        # a count line before the name
        _line(t, "Vollmilch 3,5% 1L", "2 x 1,49", "Vollmilch", quantity=2, price=2.98),
        # a weight line before the name
        _line(t, "Bananen lose", "0,736", "Bananen", weight_kg=0.736, price=1.83),
        _line(t, "Roggenbrot 500g", "Roggenbrot", price=2.29),
        _line(t, "Joghurt Natur 150g", "3 x 0,89", "Joghurt", quantity=3, price=2.67),
        _line(t, "Butter 250g", "Butter", price=2.19),
        _line(t, "Spülmittel 450ml", "Spülmittel", non_food=True, price=1.65),
    ]


DE_KINDS = {
    "Pfand": ("deposit", 0.25),
    "SUMME": ("total", 13.86),
    "Geg. Karte": ("payment", 13.86),
    "Steuer": ("tax", None),
    "A=": ("tax", 0.3),
    "B=": ("tax", 0.78),
    "Gesamtbetrag": ("tax", 13.86),
}


class TestGermanReceipt:
    """Amendment 1: quantity before the name, a deposit, a tax table."""

    async def test_a_count_before_the_name_and_the_deposit_add_up(
        self, no_unplanned_re_read
    ):
        answer = _answer(
            DE_TEXT,
            _de_all(),
            DE_KINDS,
            language="de",
            country="DE",
            receipt_total=13.86,
        )

        outcome = await reconcile_text_read(DE_TEXT, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert outcome.completeness["items_sum"] == 13.86
        assert outcome.note is None

    async def test_a_count_line_the_model_did_not_cite_stays_with_its_product(
        self, no_unplanned_re_read
    ):
        """Cited only by name, the `2 x 1,49` above it is still that milk's detail."""
        products = _de_all()
        products[0].source_lines = _at(DE_TEXT, "Vollmilch")
        answer = _answer(
            DE_TEXT, products, DE_KINDS, missed=("2 x 1,49",), receipt_total=13.86
        )

        outcome = await reconcile_text_read(DE_TEXT, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert outcome.completeness["unaccounted_lines"] == 0

    async def test_a_missed_count_and_name_are_re_read_together(
        self, no_unplanned_re_read
    ):
        read = [p for p in _de_all() if not p.name.startswith("Joghurt")]
        answer = _answer(
            DE_TEXT, read, DE_KINDS, missed=("3 x 0,89", "Joghurt"), receipt_total=13.86
        )
        no_unplanned_re_read.side_effect = LLMExtractionError("gateway down")

        outcome = await reconcile_text_read(DE_TEXT, answer, CATEGORY_OPTIONS)

        assert [n for n, _ in no_unplanned_re_read.await_args.args[0]] == [11, 12]
        (row,) = [p for p in outcome.extraction.lines if p.recovered]
        assert (row.name, row.source_lines) == ("Joghurt Natur 150g B", [11, 12])
        assert outcome.completeness["items_sum"] == 11.19
        assert "add up to 11.19" in outcome.note


class TestJoiningAnswersWithoutLineNumbers:
    """An answer that cites no lines is placed by its printed name."""

    TEXT = "SHOP\nMAITO 1,20\nMAITO 1,20\nLEIPÄ 2,10\n"

    async def test_repeated_names_are_a_multiset(self, no_unplanned_re_read):
        answer = ReceiptExtraction(
            method="text",
            lines=[ExtractedLine(name="MAITO"), ExtractedLine(name="LEIPÄ")],
            other_lines=[OtherLine(line=1, kind="header")],
        )
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer([ExtractedLine(name="MAITO")])

        outcome = await reconcile_text_read(self.TEXT, answer, CATEGORY_OPTIONS)

        assert no_unplanned_re_read.await_args.args[0] == [(3, "MAITO 1,20")]
        assert [
            (p.name, p.source_lines, p.recovered) for p in outcome.extraction.lines
        ] == [
            ("MAITO", [2], None),
            ("LEIPÄ", [4], None),
            ("MAITO", [3], "model_retry"),
        ]

    async def test_both_copies_read_means_nothing_is_missing(
        self, no_unplanned_re_read
    ):
        answer = ReceiptExtraction(
            method="text",
            lines=[
                ExtractedLine(name="MAITO"),
                ExtractedLine(name="MAITO"),
                ExtractedLine(name="LEIPÄ"),
            ],
            other_lines=[OtherLine(line=1, kind="header")],
        )

        outcome = await reconcile_text_read(self.TEXT, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert outcome.completeness["unaccounted_lines"] == 0

    async def test_a_near_miss_spelling_joins_by_similarity(self, no_unplanned_re_read):
        text = "SHOP\nPirkka miniluumutomaatti 250g 2,29\n"
        answer = ReceiptExtraction(
            method="text",
            lines=[ExtractedLine(name="Pirkka miniluumutomaati 250g")],
            other_lines=[OtherLine(line=1, kind="header")],
        )

        outcome = await reconcile_text_read(text, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert outcome.extraction.lines[0].source_lines == [2]

    async def test_a_re_read_product_citing_an_accounted_line_is_not_a_second_copy(
        self, no_unplanned_re_read
    ):
        answer = ReceiptExtraction(
            method="text",
            lines=[ExtractedLine(name="MAITO", source_lines=[2])],
            other_lines=[OtherLine(line=1, kind="header")],
        )
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer(
            [
                ExtractedLine(name="MAITO", source_lines=[2]),
                ExtractedLine(name="MAITO", source_lines=[3]),
                ExtractedLine(name="LEIPÄ", source_lines=[4]),
            ]
        )

        outcome = await reconcile_text_read(self.TEXT, answer, CATEGORY_OPTIONS)

        assert [(p.source_lines, p.recovered) for p in outcome.extraction.lines] == [
            ([2], None),
            ([3], "model_retry"),
            ([4], "model_retry"),
        ]


class TestSuspectAndUnpricedLines:
    async def test_an_other_line_with_an_amount_is_re_read(self, no_unplanned_re_read):
        text = "SHOP\nMAITO 1,20\nKAURAJUOMA 2,10\n"
        answer = ReceiptExtraction(
            method="text",
            lines=[ExtractedLine(name="MAITO", source_lines=[2])],
            other_lines=[
                OtherLine(line=1, kind="header"),
                OtherLine(line=3, kind="other", amount=2.1),
            ],
        )
        no_unplanned_re_read.side_effect = LLMExtractionError("down")

        outcome = await reconcile_text_read(text, answer, CATEGORY_OPTIONS)

        assert no_unplanned_re_read.await_args.args[0] == [(3, "KAURAJUOMA 2,10")]
        assert outcome.extraction.lines[-1].name == "KAURAJUOMA"

    async def test_when_the_money_adds_up_an_other_line_is_not_suspect(
        self, no_unplanned_re_read
    ):
        """Measured on the K receipt: loyalty lines such as "Ruokaostokset 64,70" came
        back as `other`, and re-reading them found nothing in two minutes."""
        text = "SHOP\nMAITO 1,20\nRuokaostokset 1,20\nTOTAL 1,20\n"
        answer = ReceiptExtraction(
            method="text",
            lines=[ExtractedLine(name="MAITO", source_lines=[2], price=1.2)],
            other_lines=[
                OtherLine(line=1, kind="header"),
                OtherLine(line=3, kind="other", amount=1.2),
                OtherLine(line=4, kind="total", amount=1.2),
            ],
            receipt_total=1.2,
        )

        outcome = await reconcile_text_read(text, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert outcome.completeness["unaccounted_lines"] == 0
        assert len(outcome.extraction.lines) == 1

    async def test_a_line_the_re_read_still_calls_other_is_accounted_for(
        self, no_unplanned_re_read
    ):
        text = "SHOP\nMAITO 1,20\nBONUS POINTS 2,10\n"
        answer = ReceiptExtraction(
            method="text",
            lines=[ExtractedLine(name="MAITO", source_lines=[2])],
            other_lines=[
                OtherLine(line=1, kind="header"),
                OtherLine(line=3, kind="other", amount=2.1),
            ],
        )
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = ReceiptExtraction(
            method="text", other_lines=[OtherLine(line=3, kind="other", amount=2.1)]
        )

        outcome = await reconcile_text_read(text, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_awaited_once()
        assert [p.name for p in outcome.extraction.lines] == ["MAITO"]
        assert outcome.completeness["unaccounted_lines"] == 1
        assert outcome.completeness["recovered_raw_lines"] == 0

    async def test_lines_without_an_amount_need_no_accounting(
        self, no_unplanned_re_read
    ):
        """The model lists only priced non-product lines in x, to keep its answer short."""
        text = "SHOP\nWelcome back\nMAITO 1,20\n"
        answer = ReceiptExtraction(
            method="text", lines=[ExtractedLine(name="MAITO", source_lines=[3])]
        )

        outcome = await reconcile_text_read(text, answer, CATEGORY_OPTIONS)

        no_unplanned_re_read.assert_not_awaited()
        assert outcome.completeness["unaccounted_lines"] == 0
        assert len(outcome.extraction.lines) == 1

    async def test_an_unpriced_neighbour_goes_to_the_re_read_with_its_partner(
        self, no_unplanned_re_read
    ):
        """A name printed above its price line: only the price line needs accounting,
        but the re-read must see the name too."""
        text = "SHOP\nMAITO 1,20\nJUUSTO GOUDA\n1 kpl 4,50\n"
        answer = ReceiptExtraction(
            method="text", lines=[ExtractedLine(name="MAITO", source_lines=[2])]
        )
        no_unplanned_re_read.side_effect = LLMExtractionError("down")

        outcome = await reconcile_text_read(text, answer, CATEGORY_OPTIONS)

        assert no_unplanned_re_read.await_args.args[0] == [
            (3, "JUUSTO GOUDA"),
            (4, "1 kpl 4,50"),
        ]
        assert outcome.completeness["unaccounted_lines"] == 1
        (row,) = [p for p in outcome.extraction.lines if p.recovered]
        assert (row.name, row.source_lines) == ("JUUSTO GOUDA", [3, 4])


class TestReceiptArithmetic:
    def test_line_totals_discounts_deposits_and_fees(self):
        products = [
            ExtractedLine(name="A", price=10.0),
            ExtractedLine(name="B", price=5.0),
        ]
        others = [
            OtherLine(line=1, kind="discount", amount=1.5),  # signed either way
            OtherLine(line=2, kind="deposit", amount=0.25),
            OtherLine(line=3, kind="fee", amount=2.0),
            OtherLine(line=4, kind="tax", amount=3.0),
        ]
        assert receipt_arithmetic(products, others, 15.75) == (15.75, False)

    @pytest.mark.parametrize(
        ("total", "items", "off"),
        [
            (100.0, 100.9, False),
            (100.0, 101.5, True),
            (1.0, 1.04, False),
            (1.0, 1.1, True),
        ],
    )
    def test_tolerance_is_five_cents_or_one_percent(self, total, items, off):
        products = [ExtractedLine(name="A", price=items)]
        assert receipt_arithmetic(products, [], total)[1] is off

    def test_without_prices_there_is_no_sum(self):
        assert receipt_arithmetic([ExtractedLine(name="A")], [], 3.0) == (None, False)

    def test_without_a_total_nothing_is_flagged(self):
        assert receipt_arithmetic([ExtractedLine(name="A", price=2.0)], [], None) == (
            2.0,
            False,
        )


class TestCompletenessIsPersisted:
    async def test_the_k_receipt_is_stored_with_fifteen_lines(
        self, service, pdf_receipt, sample_category, db_session, no_unplanned_re_read
    ):
        no_unplanned_re_read.side_effect = None
        no_unplanned_re_read.return_value = _retry_answer(_k_nine())
        with (
            patch(OCR, new_callable=AsyncMock, return_value=K_TEXT),
            patch(TEXT, new_callable=AsyncMock, return_value=_k_first_read()),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        structured = pdf_receipt.ocr_structured
        assert pdf_receipt.processing_status == ReceiptStatus.COMPLETED
        assert pdf_receipt.items_extracted == 15
        assert len(structured["lines"]) == 15
        assert [line["recovered"] for line in structured["lines"]].count(
            "model_retry"
        ) == 9
        assert structured["completeness"]["recovered_by_retry"] == 9
        assert structured["completeness"]["profile"] == "fi"
        assert structured["raw_completion"] == '{"p": ["six products"]}'
        assert structured["raw_completion_retry"] == '{"p": ["the rest"]}'
        assert (structured["language"], structured["country"]) == ("fi", "FI")
        assert structured["method"] == "text"
        assert structured["fallback_reason"] == (
            "9 of 15 lines were not read by the model and were recovered"
        )

    async def test_the_vision_path_checks_the_arithmetic(
        self, service, image_receipt, sample_category, db_session
    ):
        extraction = ReceiptExtraction(
            method="vision",
            lines=[ExtractedLine(name="MAITO", price=1.2)],
            receipt_total=3.3,
            raw_completion="{}",
        )
        with (
            patch(OCR, new_callable=AsyncMock, side_effect=OCRUnavailableError("down")),
            patch(VISION, new_callable=AsyncMock, return_value=extraction),
        ):
            await service.process_receipt(image_receipt)

        await db_session.refresh(image_receipt)
        structured = image_receipt.ocr_structured
        assert structured["completeness"]["text_lines"] is None
        assert structured["completeness"]["items_sum"] == 1.2
        assert structured["completeness"]["receipt_total"] == 3.3
        assert structured["fallback_reason"] == (
            "Line totals add up to 1.20 but the receipt total is 3.30"
        )
        assert structured["raw_completion"] == "{}"

    async def test_a_model_failure_is_counted_too(
        self, service, pdf_receipt, sample_category, db_session
    ):
        with (
            patch(OCR, new_callable=AsyncMock, return_value=OCR_TEXT),
            patch(
                TEXT,
                new_callable=AsyncMock,
                side_effect=LLMExtractionError("truncated"),
            ),
        ):
            await service.process_receipt(pdf_receipt)

        await db_session.refresh(pdf_receipt)
        completeness = pdf_receipt.ocr_structured["completeness"]
        assert completeness["model_lines"] == 0
        # every line is in the prompt now, the total included (Q27)
        assert completeness["text_lines"] == completeness["unaccounted_lines"] == 4


class TestPrintedPackSizeWins:
    async def test_the_printed_size_beats_the_catalogs(
        self, service, pdf_receipt, sample_category, db_session
    ):
        """Q27: "Helmitomaatti pikari 200g" matched Cherry tomato (250 g) and was stored
        as 250 g."""
        tomato = ProductMaster(
            id=uuid4(),
            canonical_name="Cherry tomato",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="weight",
            default_unit="g",
            pack_grams=Decimal("250"),
        )
        db_session.add(tomato)
        await db_session.commit()
        extraction = _extraction(
            lines=[
                ExtractedLine(
                    name="Helmitomaatti pikari 200g",
                    generic_name="Cherry tomato",
                    category="dairy",
                )
            ]
        )
        with (
            patch(OCR, new_callable=AsyncMock, return_value=_text_for(extraction)),
            patch(TEXT, new_callable=AsyncMock, return_value=extraction),
        ):
            await service.process_receipt(pdf_receipt)

        (line,) = pdf_receipt.ocr_structured["lines"]
        assert line["product_id"] == str(tomato.id)
        assert line["pack_grams"] == 200.0
