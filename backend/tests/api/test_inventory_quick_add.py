"""POST /api/inventory/quick-add and category default storage (MVP-S3)."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.db.session import get_db
from app.main import app

URL = "/api/inventory/quick-add"


@pytest.fixture
async def seeded_db(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    await seed_categories(db_session)
    await db_session.commit()
    yield db_session
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def broadcast():
    with patch(
        "app.api.endpoints.inventory.broadcast_inventory_update", new_callable=AsyncMock
    ) as mock:
        yield mock


class TestQuickAdd:
    async def test_new_product_returns_the_item(
        self, client: AsyncClient, seeded_db, broadcast
    ):
        response = await client.post(
            URL,
            json={
                "name": "Ground beef",
                "category": "meat",
                "quantity": 0.4,
                "unit": "kg",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["product_name"] == "Ground beef"
        assert body["category"] == "meat"
        assert body["category_name"]
        assert (body["unit"], body["current_quantity"]) == ("g", 400)
        assert body["location"] == "main_fridge"
        broadcast.assert_awaited_once()
        assert broadcast.await_args.kwargs["action"] == "created"

    async def test_existing_product_by_id(self, client: AsyncClient, seeded_db):
        first = (
            await client.post(
                URL,
                json={
                    "name": "Milk",
                    "category": "dairy",
                    "quantity": 10,
                    "unit": "dl",
                },
            )
        ).json()

        response = await client.post(
            URL,
            json={
                "product_id": first["product_master_id"],
                "quantity": 2,
                "unit": "pcs",
                "expiry_date": "2026-10-01",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["product_master_id"] == first["product_master_id"]
        assert (body["expiry_date"], body["expiry_source"]) == ("2026-10-01", "manual")

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            ({"name": "Tofu", "quantity": 1, "unit": "pcs"}, "Category required"),
            (
                {
                    "product_id": "00000000-0000-0000-0000-000000000000",
                    "quantity": 1,
                    "unit": "pcs",
                },
                "not found",
            ),
            (
                {"name": "Tofu", "category": "vegan", "quantity": 1, "unit": "pcs"},
                "Unknown category",
            ),
        ],
    )
    async def test_invalid_product_is_400(
        self, client: AsyncClient, seeded_db, broadcast, payload, message
    ):
        response = await client.post(URL, json=payload)

        assert response.status_code == 400
        assert message in response.json()["detail"]
        broadcast.assert_not_awaited()

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "Milk", "category": "dairy", "quantity": 0, "unit": "dl"},
            {"name": "Milk", "category": "dairy", "quantity": 1, "unit": "oz"},
            {"quantity": 1, "unit": "pcs"},
        ],
    )
    async def test_invalid_payload_is_422(
        self, client: AsyncClient, seeded_db, payload
    ):
        assert (await client.post(URL, json=payload)).status_code == 422


class TestCategoryDefaultStorage:
    async def test_categories_say_where_their_products_go(
        self, client: AsyncClient, seeded_db
    ):
        categories = {c["id"]: c for c in (await client.get("/api/categories")).json()}

        assert categories["frozen"]["default_storage"] == "freezer"
        assert categories["bread"]["default_storage"] == "pantry"
        assert categories["dairy"]["default_storage"] == "refrigerator"
