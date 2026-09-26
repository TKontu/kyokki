"""Q19: every path that creates a product asks the estimator about it, in the background.

Quick add, the agents' stock add and receipt confirm each create products with a placeholder
shelf life. Each schedules the estimate after its commit, so the response is the one it always
was - built before the model has said anything - and the product's own number lands shortly
after, moving the food it dated. `POST /products` takes a number the cook typed, so it is the
cook's and nothing is scheduled.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import SEED_CATEGORIES
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.services import shelf_life_on_create
from app.services.catalog_estimates import Estimate, EstimateRequest
from app.services.llm_extractor import LLMExtractionError
from app.services.shelf_life_on_create import schedule_estimates

BOUGHT = date(2026, 9, 1)
PLACEHOLDER = {c["id"]: c["default_shelf_life_days"] for c in SEED_CATEGORIES}
ESTIMATED = 14


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, session_factory) -> None:
    """The task opens its own session; here it is the test's, so its rows are visible."""
    monkeypatch.setattr(shelf_life_on_create, "open_session", session_factory)


@pytest.fixture
def estimator():
    """Answers ESTIMATED days for every product it is asked about."""

    async def answer(products: list[EstimateRequest]) -> list[Estimate]:
        return [
            Estimate(id=p.id, shelf_life_days=ESTIMATED, opened_shelf_life_days=None)
            for p in products
        ]

    mock = AsyncMock(side_effect=answer)
    with patch("app.services.catalog_estimates.estimate_shelf_lives", new=mock):
        yield mock


@pytest.fixture
def unreachable():
    mock = AsyncMock(side_effect=LLMExtractionError("gateway is down"))
    with patch("app.services.catalog_estimates.estimate_shelf_lives", new=mock):
        yield mock


async def _product(db: AsyncSession, product_id: UUID | str) -> ProductMaster:
    product = await db.get(ProductMaster, UUID(str(product_id)), populate_existing=True)
    assert product is not None
    return product


async def _item(db: AsyncSession, item_id: UUID | str) -> InventoryItem:
    item = await db.get(InventoryItem, UUID(str(item_id)), populate_existing=True)
    assert item is not None
    return item


QUICK_ADD = {
    "name": "Tomato",
    "category": "produce",
    "quantity": 4,
    "unit": "pcs",
    "purchase_date": BOUGHT.isoformat(),
}


class TestQuickAdd:
    async def test_a_new_product_gets_its_own_estimate(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        response = await client.post("/api/inventory/quick-add", json=QUICK_ADD)

        assert response.status_code == 201
        body = response.json()
        # The response did not wait for the model: it carries the placeholder's date...
        assert body["expiry_date"] == str(
            BOUGHT + timedelta(days=PLACEHOLDER["produce"])
        )
        estimator.assert_awaited_once()
        # ...and the estimate landed afterwards, moving the food with it.
        product = await _product(seeded_db, body["product_master_id"])
        assert (product.default_shelf_life_days, product.shelf_life_source) == (
            ESTIMATED,
            "model",
        )
        item = await _item(seeded_db, body["id"])
        assert item.expiry_date == BOUGHT + timedelta(days=ESTIMATED)

    async def test_an_existing_product_is_not_asked_about(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        await client.post("/api/inventory/quick-add", json=QUICK_ADD)
        estimator.reset_mock()

        response = await client.post("/api/inventory/quick-add", json=QUICK_ADD)

        assert response.status_code == 201
        estimator.assert_not_awaited()

    async def test_a_model_that_cannot_answer_changes_nothing_for_the_cook(
        self, client: AsyncClient, seeded_db: AsyncSession, unreachable
    ) -> None:
        response = await client.post("/api/inventory/quick-add", json=QUICK_ADD)

        assert response.status_code == 201
        unreachable.assert_awaited_once()
        product = await _product(seeded_db, response.json()["product_master_id"])
        assert (product.default_shelf_life_days, product.shelf_life_source) == (
            PLACEHOLDER["produce"],
            "category",
        )


class TestStockAdd:
    async def test_a_new_product_gets_its_own_estimate(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        response = await client.post("/api/stock/add", json=QUICK_ADD)

        assert response.status_code == 201
        body = response.json()
        assert body["product_created"] is True
        assert body["item"]["expiry_date"] == str(
            BOUGHT + timedelta(days=PLACEHOLDER["produce"])
        )
        product = await _product(seeded_db, body["item"]["product_master_id"])
        assert (product.default_shelf_life_days, product.shelf_life_source) == (
            ESTIMATED,
            "model",
        )
        item = await _item(seeded_db, body["item"]["id"])
        assert item.expiry_date == BOUGHT + timedelta(days=ESTIMATED)

    async def test_an_existing_product_is_not_asked_about(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        await client.post("/api/stock/add", json=QUICK_ADD)
        estimator.reset_mock()

        response = await client.post("/api/stock/add", json=QUICK_ADD)

        assert response.json()["product_created"] is False
        estimator.assert_not_awaited()

    async def test_an_idempotent_replay_schedules_no_estimate(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        headers = {"Idempotency-Key": "estimate-replay"}
        first = await client.post("/api/stock/add", json=QUICK_ADD, headers=headers)
        assert first.json()["product_created"] is True
        estimator.assert_awaited_once()
        estimator.reset_mock()

        with patch(
            "app.api.endpoints.stock.schedule_estimates", wraps=schedule_estimates
        ) as scheduled:
            again = await client.post("/api/stock/add", json=QUICK_ADD, headers=headers)

        assert again.status_code == 201
        assert again.headers.get("Idempotent-Replayed") == "true"
        # The replayed body still says the product was new, and still nothing is asked.
        assert again.json() == first.json()
        scheduled.assert_not_called()
        estimator.assert_not_awaited()

    async def test_a_model_that_cannot_answer_still_returns_201(
        self, client: AsyncClient, seeded_db: AsyncSession, unreachable
    ) -> None:
        response = await client.post("/api/stock/add", json=QUICK_ADD)

        assert response.status_code == 201
        product = await _product(
            seeded_db, response.json()["item"]["product_master_id"]
        )
        assert product.shelf_life_source == "category"


class TestReceiptConfirm:
    async def _receipt(self, db: AsyncSession) -> Receipt:
        receipt = Receipt(
            image_path="receipts/q19.jpg",
            processing_status="completed",
            ocr_structured={"lines": []},
            items_extracted=0,
        )
        db.add(receipt)
        await db.commit()
        return receipt

    def _item(self, name: str, category: str) -> dict:
        return {
            "name": name,
            "category": category,
            "quantity": 1,
            "unit": "pcs",
            "purchase_date": BOUGHT.isoformat(),
        }

    async def test_every_new_product_is_estimated_in_one_request(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        receipt = await self._receipt(seeded_db)

        response = await client.post(
            f"/api/receipts/{receipt.id}/confirm",
            json={
                "items": [
                    self._item("Tomato", "produce"),
                    self._item("Orange", "fruits"),
                ]
            },
        )

        assert response.status_code == 200
        assert response.json()["products_created"] == 2
        estimator.assert_awaited_once()
        (asked,) = estimator.await_args.args
        assert sorted(r.name for r in asked) == ["Orange", "Tomato"]

        items = (
            (
                await seeded_db.execute(
                    select(InventoryItem)
                    .where(InventoryItem.receipt_id == receipt.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        assert len(items) == 2
        for item in items:
            product = await _product(seeded_db, item.product_master_id)
            assert product.shelf_life_source == "model"
            assert item.expiry_date == BOUGHT + timedelta(days=ESTIMATED)

    async def test_a_receipt_of_known_products_asks_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        await client.post("/api/inventory/quick-add", json=QUICK_ADD)
        estimator.reset_mock()
        receipt = await self._receipt(seeded_db)

        response = await client.post(
            f"/api/receipts/{receipt.id}/confirm",
            json={"items": [self._item("Tomato", "produce")]},
        )

        assert response.json()["products_created"] == 0
        estimator.assert_not_awaited()


class TestCreateProduct:
    PRODUCT = {
        "canonical_name": "Ground beef",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 2,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def test_the_cooks_number_is_theirs_and_nothing_is_scheduled(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        response = await client.post("/api/products", json=self.PRODUCT)

        assert response.status_code == 201
        assert response.json()["shelf_life_source"] == "cook"
        assert response.json()["default_shelf_life_days"] == 2
        estimator.assert_not_awaited()

    async def test_no_estimate_path_changes_it_later(
        self, client: AsyncClient, seeded_db: AsyncSession, estimator
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        await client.post("/api/products/estimate?apply=true&scope=all")
        await shelf_life_on_create.estimate_new_products([UUID(product["id"])])

        after = await _product(seeded_db, product["id"])
        assert (after.default_shelf_life_days, after.shelf_life_source) == (2, "cook")
        estimator.assert_not_awaited()
