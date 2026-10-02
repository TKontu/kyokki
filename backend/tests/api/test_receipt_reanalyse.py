"""POST /api/receipts/{id}/lines/{line_id}/reanalyse (Q38)."""

import json
from datetime import date
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.receipt import Receipt
from app.services import receipt_line_reanalyse
from app.services.llm_http import LLMAuthError

PURCHASED = date(2026, 9, 26)


@pytest.fixture
async def test_db(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield db_session
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_category(test_db: AsyncSession) -> Category:
    category = Category(
        id="dairy",
        display_name="Dairy",
        icon="🥛",
        default_shelf_life_days=7,
        sort_order=1,
    )
    test_db.add(category)
    await test_db.commit()
    await test_db.refresh(category)
    return category


async def _receipt(db: AsyncSession, *, status: str = "completed", **fields) -> Receipt:
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
    return LLMAuthError("auth failed", request=request, response=response)


class TestReanalyseEndpoint:
    async def test_unknown_receipt_is_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.post(
            f"/api/receipts/{uuid4()}/lines/{uuid4()}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 404

    async def test_unknown_line_is_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        receipt = await _receipt(test_db, ocr_structured={"lines": []})

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{uuid4()}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 404

    async def test_a_confirmed_receipt_is_409(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db,
            status="confirmed",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 409

    async def test_a_processing_receipt_is_409(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db,
            status="processing",
            ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]},
        )

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 409

    async def test_a_hint_over_200_characters_is_400(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db, ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]}
        )

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse",
            json={"hint": "x" * 201},
        )
        assert response.status_code == 400

    async def test_success_returns_the_updated_item(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db,
            ocr_structured={
                "lines": [
                    {
                        "name": "PESTO JA CASHEW",
                        "price": 2.49,
                        "line_id": str(line_id),
                        "generic_name": "Dip",
                    }
                ]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "Cashew nuts", "c": "dairy"}))

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse",
            json={"hint": "cashew nuts"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["line_id"] == str(line_id)
        assert body["name"] == "PESTO JA CASHEW"
        assert body["price"] == 2.49
        assert body["generic_name"] == "Cashew nuts"
        assert body["suggested_category"] == "dairy"

        # Persisted: reloading the receipt shows it (acceptance criterion)
        reread = await client.get(f"/api/receipts/{receipt.id}")
        reread_item = reread.json()["items"][0]
        assert reread_item["generic_name"] == "Cashew nuts"

    async def test_an_empty_hint_is_the_same_as_none(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db, ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]}
        )
        _stub(monkeypatch, json.dumps({"g": "Something", "c": "dairy"}))

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse",
            json={"hint": "   "},
        )
        assert response.status_code == 200, response.text

    async def test_an_invalid_model_answer_is_502(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db, ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]}
        )
        _stub(monkeypatch, json.dumps({"g": "", "c": "dairy"}))

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 502

    async def test_an_auth_error_is_503(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db, ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]}
        )
        _stub(monkeypatch, raises=_auth_error())

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 503

    async def test_a_timeout_is_504(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ):
        line_id = uuid4()
        receipt = await _receipt(
            test_db, ocr_structured={"lines": [{"name": "X", "line_id": str(line_id)}]}
        )
        _stub(monkeypatch, raises=httpx.ReadTimeout("slow"))

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_id}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 504

    async def test_a_hand_edited_row_is_not_touched_without_confirming(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_category: Category,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The overwrite-confirmation itself is a frontend behaviour (Q38's acceptance
        criterion "a hand-edited row asks before a re-analyse overwrites it"); the API
        always answers with the fresh result; it is the frontend's job to ask first and
        only apply it when the cook agrees. Covered in the frontend tests; this is the
        contract the API side provides: re-analysing never silently touches any row but
        the one named in the path.
        """
        line_a, line_b = uuid4(), uuid4()
        receipt = await _receipt(
            test_db,
            ocr_structured={
                "lines": [
                    {"name": "A", "line_id": str(line_a), "generic_name": "A-generic"},
                    {"name": "B", "line_id": str(line_b), "generic_name": "B-generic"},
                ]
            },
        )
        _stub(monkeypatch, json.dumps({"g": "A-new", "c": "dairy"}))

        response = await client.post(
            f"/api/receipts/{receipt.id}/lines/{line_a}/reanalyse", json={"hint": None}
        )
        assert response.status_code == 200, response.text

        reread = await client.get(f"/api/receipts/{receipt.id}")
        items = {item["line_id"]: item for item in reread.json()["items"]}
        assert items[str(line_a)]["generic_name"] == "A-new"
        # The other line is untouched
        assert items[str(line_b)]["generic_name"] == "B-generic"
