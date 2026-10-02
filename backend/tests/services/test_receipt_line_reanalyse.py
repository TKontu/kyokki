"""Re-ask the model for one receipt line, with an optional hint from the cook (Q38)."""

import asyncio
import json
from datetime import UTC, date, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.category import Category
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.services import receipt_line_reanalyse
from app.services.llm_extractor import CategoryOption
from app.services.llm_http import LLMAuthError
from app.services.matching_service import normalize_receipt_name
from app.services.product_selection import select_products as real_select_products
from app.services.receipt_confirm import UNKNOWN_CHAIN

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


class TestResolutionWithCatalog:
    """F4: the real resolver tiers, exercised for this call site with a real catalog."""

    async def test_a_matching_catalog_name_resolves(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = ProductMaster(
            id=uuid4(),
            canonical_name="Cashew nuts",
            category="dairy",
            storage_type="pantry",
            default_shelf_life_days=180,
            unit_type="count",
            default_unit="pcs",
        )
        db_session.add(product)
        await db_session.commit()

        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={
                "lines": [{"name": "PESTO JA CASHEW", "line_id": str(line_id)}]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "Cashew nuts", "c": "dairy"}))

        item = await receipt_line_reanalyse.reanalyse_line(
            db_session, receipt.id, line_id, None
        )

        assert item.product_id == product.id
        assert item.match_source == "name"

    async def test_an_alias_for_the_printed_name_resolves(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = ProductMaster(
            id=uuid4(),
            canonical_name="Cashew nuts",
            category="dairy",
            storage_type="pantry",
            default_shelf_life_days=180,
            unit_type="count",
            default_unit="pcs",
        )
        db_session.add(product)
        await db_session.commit()
        alias = StoreProductAlias(
            product_master_id=product.id,
            store_chain=UNKNOWN_CHAIN,
            receipt_name=normalize_receipt_name("PESTO JA CASHEW"),
            source="cook",
            confidence_score=1.0,
            manually_verified=True,
            occurrence_count=1,
            last_seen=datetime.now(UTC),
        )
        db_session.add(alias)
        await db_session.commit()

        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            store_chain=None,
            ocr_structured={
                "lines": [{"name": "PESTO JA CASHEW", "line_id": str(line_id)}]
            },
        )
        # A different `g` from the model: the alias is keyed on the printed name, not
        # the generic name, so it wins regardless of what the model answered.
        _stub(monkeypatch, json.dumps({"g": "Something else entirely", "c": "dairy"}))

        item = await receipt_line_reanalyse.reanalyse_line(
            db_session, receipt.id, line_id, None
        )

        assert item.product_id == product.id
        assert item.match_source == "alias"

    async def test_selection_is_asked_and_a_failure_still_returns_unmatched(
        self,
        db_session: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Neither alias nor name settles this line, so the resolver shortlists it and
        asks the model to choose (`product_selection.select_products`, its own
        `post_chat` stubbed here, separately from the re-analyse prompt's). A selection
        failure (`LLMExtractionError`) must not fail the re-analyse: it comes back
        unmatched, the line's fresh name and category still applied.
        """
        # The autouse `_no_model_selection` fixture normally replaces
        # `select_products` outright; undone here so the real function - and its own
        # `post_chat` - runs, per the review's request to exercise that path for real.
        monkeypatch.setattr(
            "app.services.product_resolution.select_products", real_select_products
        )

        # Same category as the line's resolved answer, so the retriever offers it as a
        # candidate (a category match alone is enough - no name similarity needed).
        other = ProductMaster(
            id=uuid4(),
            canonical_name="Peanut butter",
            category="dairy",
            storage_type="pantry",
            default_shelf_life_days=180,
            unit_type="count",
            default_unit="pcs",
        )
        db_session.add(other)
        await db_session.commit()

        line_id = uuid4()
        receipt = await _receipt(
            db_session,
            status="completed",
            ocr_structured={
                "lines": [{"name": "PESTO JA CASHEW", "line_id": str(line_id)}]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "Cashew nuts", "c": "dairy"}))

        async def failing_post_chat(client, payload, *, budget):
            raise httpx.ConnectError("gateway down")

        monkeypatch.setattr(
            "app.services.product_selection.post_chat", failing_post_chat
        )

        item = await receipt_line_reanalyse.reanalyse_line(
            db_session, receipt.id, line_id, None
        )

        assert item.generic_name == "Cashew nuts"
        assert item.product_id is None
        # Unresolved is its own vocabulary value, not absent (`ResolutionSource`'s "none")
        assert item.match_source == "none"


class TestLockTiming:
    """F1: the receipt row must not stay locked across the model call."""

    async def test_the_lock_is_taken_only_after_the_model_answers(
        self,
        db_engine,
        committed_db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        line_id = uuid4()
        receipt = await _receipt(
            committed_db_session,
            status="completed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )

        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_ask_model(prompt: str) -> str:
            started.set()
            await release.wait()
            return json.dumps({"g": "Something", "c": None})

        monkeypatch.setattr(receipt_line_reanalyse, "_ask_model", slow_ask_model)

        factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def run_reanalyse() -> object:
            async with factory() as session:
                return await receipt_line_reanalyse.reanalyse_line(
                    session, receipt.id, line_id, None
                )

        task = asyncio.create_task(run_reanalyse())
        await asyncio.wait_for(started.wait(), timeout=10)

        # While the model call is "in flight", a second connection can lock the same
        # row without waiting at all: phase 1 holds no lock (F1).
        async with factory() as prober:
            await asyncio.wait_for(
                prober.execute(
                    text("SELECT id FROM receipt WHERE id = :id FOR UPDATE NOWAIT"),
                    {"id": str(receipt.id)},
                ),
                timeout=5,
            )
            await prober.rollback()

        release.set()
        item = await asyncio.wait_for(task, timeout=10)
        assert item.generic_name == "Something"

    async def test_phase_two_sees_a_change_committed_during_the_model_call(
        self,
        db_engine,
        committed_db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Locking late (F1) is only safe if the re-check it buys actually reads fresh
        data. `receipt` stays in this session's identity map across both phases, and
        SQLAlchemy does not refresh an identity-mapped object's attributes from a plain
        re-query - `populate_existing` is what makes the phase 2 re-check see a change
        another session committed while the model call was running, rather than the
        phase 1 snapshot."""
        line_id = uuid4()
        receipt = await _receipt(
            committed_db_session,
            status="completed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )

        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_ask_model(prompt: str) -> str:
            started.set()
            await release.wait()
            return json.dumps({"g": "Something", "c": None})

        monkeypatch.setattr(receipt_line_reanalyse, "_ask_model", slow_ask_model)

        factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async def run_reanalyse() -> object:
            async with factory() as session:
                return await receipt_line_reanalyse.reanalyse_line(
                    session, receipt.id, line_id, None
                )

        task = asyncio.create_task(run_reanalyse())
        await asyncio.wait_for(started.wait(), timeout=10)

        # A concurrent re-read replaces the line while the model call is in flight -
        # same line_id gone, a different one in its place.
        async with factory() as writer:
            other = await writer.get(Receipt, receipt.id)
            other.ocr_structured = {"lines": [{"name": "Y", "line_id": str(uuid4())}]}
            await writer.commit()

        release.set()
        with pytest.raises(receipt_line_reanalyse.LineNotFound):
            await asyncio.wait_for(task, timeout=10)
