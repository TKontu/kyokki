"""Re-ask the model for one receipt line, with an optional hint from the cook (Q38)."""

import json
from datetime import date
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.services import receipt_line_reanalyse
from app.services.llm_extractor import CategoryOption
from app.services.llm_http import LLMAuthError

PURCHASED = date(2026, 9, 26)


async def _receipt(db: AsyncSession, *, status: str, **fields) -> Receipt:
    fields.setdefault("image_path", f"data/receipts/{uuid4()}.jpg")
    fields.setdefault("purchase_date", PURCHASED)
    receipt = Receipt(
        id=uuid4(),
        processing_status=status,
        items_extracted=0,
        items_matched=0,
        **fields,
    )
    db.add(receipt)
    await db.commit()
    await db.refresh(receipt)
    return receipt


def _stub(monkeypatch: pytest.MonkeyPatch, content: str | None = None, *, raises=None):
    """Replace the module's ``post_chat`` with one answering ``content`` (or raising)."""

    async def fake_post_chat(client, payload, *, budget):
        if raises is not None:
            raise raises
        request = httpx.Request("POST", "http://gateway.invalid/v1/chat/completions")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
            request=request,
        )

    monkeypatch.setattr(receipt_line_reanalyse, "post_chat", fake_post_chat)


def _auth_error() -> LLMAuthError:
    request = httpx.Request("POST", "http://gateway.invalid/v1/chat/completions")
    response = httpx.Response(401, request=request)
    return LLMAuthError(
        "the LLM gateway rejected LLM_API_KEY (HTTP 401)",
        request=request,
        response=response,
    )


class TestBuildPrompt:
    """The prompt (one small request, no catalog, the hint outranks the printed text)."""

    def test_it_carries_the_printed_line(self) -> None:
        request = receipt_line_reanalyse.LineRequest(
            printed="PESTO JA CASHEW",
            price=2.49,
            language=None,
            country=None,
            hint=None,
        )
        prompt = receipt_line_reanalyse.build_prompt(
            request, [CategoryOption(id="dairy", name="Dairy")]
        )
        assert "PESTO JA CASHEW" in prompt
        assert "2.49" in prompt
        assert "dairy (Dairy)" in prompt

    def test_the_hint_is_included_and_outranks_the_printed_text(self) -> None:
        request = receipt_line_reanalyse.LineRequest(
            printed="PESTO JA CASHEW",
            price=None,
            language=None,
            country=None,
            hint="cashew nuts",
        )
        prompt = receipt_line_reanalyse.build_prompt(request, [])
        assert "cashew nuts" in prompt
        assert "outranks the printed text" in prompt

    def test_a_different_kind_of_food_is_a_different_product(self) -> None:
        request = receipt_line_reanalyse.LineRequest(
            printed="X", price=None, language=None, country=None, hint=None
        )
        prompt = receipt_line_reanalyse.build_prompt(request, [])
        assert "A different kind of food is a different product" in prompt

    def test_it_offers_no_catalog_to_copy(self) -> None:
        """Q37's failure mode: the catalog must not be offered as names to copy."""
        request = receipt_line_reanalyse.LineRequest(
            printed="X", price=None, language=None, country=None, hint=None
        )
        prompt = receipt_line_reanalyse.build_prompt(request, [])
        assert "candidate" not in prompt.lower()
        assert "catalog" not in prompt.lower()

    def test_locale_is_included_when_stored(self) -> None:
        request = receipt_line_reanalyse.LineRequest(
            printed="X", price=None, language="fi", country="FI", hint=None
        )
        prompt = receipt_line_reanalyse.build_prompt(request, [])
        assert "fi/FI" in prompt


class TestParseAnswer:
    def test_a_food_answer(self) -> None:
        answer = receipt_line_reanalyse.parse_answer(
            json.dumps({"g": "Cashew nuts", "c": "dairy"}), {"dairy"}
        )
        assert answer == ("Cashew nuts", "dairy", False)

    def test_a_household_answer_clears_the_category(self) -> None:
        answer = receipt_line_reanalyse.parse_answer(
            json.dumps({"g": "Cleaning cloth", "c": "household"}), {"dairy"}
        )
        assert answer == ("Cleaning cloth", None, True)

    def test_a_null_category_is_kept_null(self) -> None:
        answer = receipt_line_reanalyse.parse_answer(
            json.dumps({"g": "Something", "c": None}), {"dairy"}
        )
        assert answer == ("Something", None, False)

    def test_a_category_matches_case_insensitively(self) -> None:
        _, category, _ = receipt_line_reanalyse.parse_answer(
            json.dumps({"g": "X", "c": "DAIRY"}), {"dairy"}
        )
        assert category == "dairy"

    def test_an_empty_name_is_rejected(self) -> None:
        with pytest.raises(receipt_line_reanalyse.InvalidModelAnswer):
            receipt_line_reanalyse.parse_answer(
                json.dumps({"g": "   ", "c": "dairy"}), {"dairy"}
            )

    def test_an_unknown_category_is_rejected(self) -> None:
        with pytest.raises(receipt_line_reanalyse.InvalidModelAnswer):
            receipt_line_reanalyse.parse_answer(
                json.dumps({"g": "X", "c": "not-a-category"}), {"dairy"}
            )


class TestReanalyseLine:
    """``reanalyse_line`` end to end, model stubbed."""

    async def test_unknown_receipt_raises(self, db_session: AsyncSession) -> None:
        with pytest.raises(receipt_line_reanalyse.ReceiptNotFound):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, uuid4(), uuid4(), None
            )

    async def test_a_confirmed_receipt_is_not_reanalysable(
        self, db_session: AsyncSession
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="confirmed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )
        with pytest.raises(receipt_line_reanalyse.ReceiptNotReanalysable):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )

    async def test_a_processing_receipt_is_not_reanalysable(
        self, db_session: AsyncSession
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="processing",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )
        with pytest.raises(receipt_line_reanalyse.ReceiptNotReanalysable):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )

    async def test_unknown_line_raises(self, db_session: AsyncSession) -> None:
        receipt = await _receipt(
            db_session, status="completed", ocr_structured={"lines": []}
        )
        with pytest.raises(receipt_line_reanalyse.LineNotFound):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, uuid4(), None
            )

    async def test_a_hint_over_200_characters_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        with pytest.raises(receipt_line_reanalyse.InvalidHint):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, uuid4(), uuid4(), "x" * 201
            )

    async def test_success_updates_and_returns_the_line(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            store_chain="k-group",
            ocr_structured={
                "lines": [
                    {
                        "name": "PESTO JA CASHEW",
                        "price": 2.49,
                        "line_id": str(line_id),
                        "generic_name": "Dip",
                        "category": None,
                    }
                ],
                "language": "fi",
                "country": "FI",
            },
        )
        _stub(monkeypatch, json.dumps({"g": "Cashew nuts", "c": "dairy"}))

        item = await receipt_line_reanalyse.reanalyse_line(
            db_session, receipt.id, line_id, "cashew nuts"
        )

        assert item.line_id == line_id
        assert item.generic_name == "Cashew nuts"
        assert item.suggested_category == "dairy"
        assert item.non_food is False

        await db_session.refresh(receipt)
        line = receipt.ocr_structured["lines"][0]
        assert line["generic_name"] == "Cashew nuts"
        assert line["category"] == "dairy"
        assert line["reanalysed"] is True
        assert line["reanalyse_hint"] == "cashew nuts"
        # Nothing is learned (spec): no alias, no product
        aliases = (await db_session.execute(select(StoreProductAlias))).scalars().all()
        assert aliases == []

    async def test_a_non_food_answer_clears_the_category(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={
                "lines": [
                    {
                        "name": "SIENILIINA",
                        "line_id": str(line_id),
                        "category": "dairy",
                    }
                ]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "Cleaning cloth", "c": "household"}))

        item = await receipt_line_reanalyse.reanalyse_line(
            db_session, receipt.id, line_id, None
        )

        assert item.non_food is True
        assert item.suggested_category is None

    async def test_without_a_hint_the_line_still_updates(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )
        _stub(monkeypatch, json.dumps({"g": "Something", "c": None}))

        item = await receipt_line_reanalyse.reanalyse_line(
            db_session, receipt.id, line_id, None
        )

        assert item.generic_name == "Something"
        await db_session.refresh(receipt)
        assert receipt.ocr_structured["lines"][0]["reanalyse_hint"] is None

    async def test_an_empty_generic_name_leaves_the_line_unchanged(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={
                "lines": [{"name": "X", "line_id": str(line_id), "generic_name": "Dip"}]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "   ", "c": "dairy"}))

        with pytest.raises(receipt_line_reanalyse.InvalidModelAnswer):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )

        await db_session.refresh(receipt)
        assert receipt.ocr_structured["lines"][0]["generic_name"] == "Dip"

    async def test_an_unknown_category_leaves_the_line_unchanged(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={
                "lines": [{"name": "X", "line_id": str(line_id), "generic_name": "Dip"}]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "Cashew nuts", "c": "not-a-category"}))

        with pytest.raises(receipt_line_reanalyse.InvalidModelAnswer):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )

        await db_session.refresh(receipt)
        assert receipt.ocr_structured["lines"][0]["generic_name"] == "Dip"

    async def test_an_auth_error_is_unavailable(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )
        _stub(monkeypatch, raises=_auth_error())

        with pytest.raises(receipt_line_reanalyse.ReanalyseUnavailable):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )

    async def test_an_unreachable_gateway_is_unavailable(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )
        _stub(monkeypatch, raises=httpx.ConnectError("refused"))

        with pytest.raises(receipt_line_reanalyse.ReanalyseUnavailable):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )

    async def test_a_timeout_is_reported_distinctly(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )
        _stub(monkeypatch, raises=httpx.ReadTimeout("slow"))

        with pytest.raises(receipt_line_reanalyse.ReanalyseTimedOut):
            await receipt_line_reanalyse.reanalyse_line(
                db_session, receipt.id, line_id, None
            )
