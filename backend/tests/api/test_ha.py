"""Home Assistant REST endpoints (docs/HOME_ASSISTANT_SPEC.md): /api/ha/*.

Each GET's test pins the JSON keys the spec (as the planner's rulings narrow it) promises
HA's REST sensor platform and voice intents. The two POSTs are tested for idempotency,
broadcasting and the agent-style errors the same way AG2's stock routes are.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_tokens import hash_secret
from app.core.config import settings
from app.models.idempotency_key import IdempotencyKey
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.shopping_list_item import ShoppingListItem

TODAY = date.today()

READ_SECRET = "ha-read-secret-0123456789"
WRITE_SECRET = "ha-write-secret-9876543210"


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
def tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "KYOKKI_API_TOKENS",
        [
            f"dashboard:read:{hash_secret(READ_SECRET)}",
            f"hermes:write:{hash_secret(WRITE_SECRET)}",
        ],
    )


@pytest.fixture
def broadcast():
    with (
        patch(
            "app.api.endpoints.ha.broadcast_inventory_update", new_callable=AsyncMock
        ) as inventory_mock,
        patch(
            "app.api.endpoints.ha.broadcast_shopping_list_update",
            new_callable=AsyncMock,
        ) as shopping_mock,
    ):
        yield inventory_mock, shopping_mock


@pytest.fixture
async def db(seeded_db: AsyncSession) -> AsyncSession:
    return seeded_db


async def _product(
    db: AsyncSession,
    name: str,
    *,
    unit: str = "dl",
    category: str = "dairy",
    min_stock_quantity: Decimal | None = None,
    reorder_quantity: Decimal | None = None,
) -> ProductMaster:
    unit_type = {"dl": "volume", "g": "weight", "pcs": "count"}[unit]
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type=unit_type,
        default_unit=unit,
        min_stock_quantity=min_stock_quantity,
        reorder_quantity=reorder_quantity,
    )
    db.add(product)
    db.add(
        ProductName(
            product_master_id=product.id, name=name.casefold(), source="canonical"
        )
    )
    await db.commit()
    return product


async def _item(
    db: AsyncSession,
    product: ProductMaster,
    quantity: str,
    *,
    initial: str | None = None,
    unit: str = "dl",
    expires_in: int = 7,
    location: str = "main_fridge",
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(initial if initial is not None else quantity),
        current_quantity=Decimal(quantity),
        unit=unit,
        status="sealed",
        expiry_date=TODAY + timedelta(days=expires_in),
        location=location,
    )
    db.add(item)
    await db.commit()
    return item


async def _count(db: AsyncSession, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar())


class TestStatus:
    async def test_response_shape(self, client: AsyncClient, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", expires_in=1)
        await _item(db, milk, "1", expires_in=-2)

        response = await client.get("/api/ha/status")

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {
            "total_items",
            "expiring_within_3_days",
            "expired",
            "by_location",
            "last_updated",
        }
        assert body["total_items"] == 2
        assert body["expired"] == 1
        # F1: the already-expired item does not also count as "expiring".
        assert body["expiring_within_3_days"] == 1
        assert body["by_location"] == {"main_fridge": 2}


class TestExpiring:
    async def test_response_shape(self, client: AsyncClient, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", initial="10", expires_in=1)

        response = await client.get("/api/ha/expiring")

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {"items", "count"}
        assert body["count"] == 1
        (item,) = body["items"]
        assert set(item.keys()) == {
            "id",
            "name",
            "category",
            "expiry_date",
            "days_until_expiry",
            "quantity_percent",
            "expired",
        }
        assert item["name"] == "Milk"
        assert item["category"] == "dairy"
        assert item["days_until_expiry"] == 1
        assert item["quantity_percent"] == 50
        assert item["expired"] is False

    async def test_expired_flag_per_item(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "1", expires_in=-2)
        await _item(db, milk, "1", expires_in=1)

        response = await client.get("/api/ha/expiring?days=3")

        items = {
            item["days_until_expiry"]: item["expired"]
            for item in response.json()["items"]
        }
        assert items == {-2: True, 1: False}

    async def test_days_query_param(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "1", expires_in=5)

        default_window = await client.get("/api/ha/expiring")
        wider_window = await client.get("/api/ha/expiring?days=7")

        assert default_window.json()["count"] == 0
        assert wider_window.json()["count"] == 1

    async def test_limit_query_param(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk")
        for day in range(5):
            await _item(db, milk, "1", expires_in=day)

        response = await client.get("/api/ha/expiring?days=10&limit=2")

        assert response.json()["count"] == 2


class TestLowStock:
    async def test_response_shape(self, client: AsyncClient, db: AsyncSession) -> None:
        eggs = await _product(
            db,
            "Eggs",
            min_stock_quantity=Decimal("10"),
            reorder_quantity=Decimal("12"),
        )
        await _item(db, eggs, "4")

        response = await client.get("/api/ha/low-stock")

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {"items", "count"}
        assert body["count"] == 1
        (item,) = body["items"]
        assert set(item.keys()) == {
            "id",
            "name",
            "category",
            "quantity_percent",
            "on_shopping_list",
        }
        assert item["name"] == "Eggs"
        assert item["quantity_percent"] == 40
        assert item["on_shopping_list"] is False

    async def test_writes_nothing(self, client: AsyncClient, db: AsyncSession) -> None:
        eggs = await _product(
            db, "Eggs", min_stock_quantity=Decimal("10"), reorder_quantity=Decimal("12")
        )
        await _item(db, eggs, "4")

        await client.get("/api/ha/low-stock")

        assert await _count(db, ShoppingListItem) == 0


class TestConsume:
    async def test_response_shape_and_broadcast(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        inventory_broadcast, _ = broadcast
        milk = await _product(db, "Milk")
        await _item(db, milk, "10")

        response = await client.post(
            "/api/ha/consume", json={"name": "milk", "amount": 3, "unit": "dl"}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {"success", "item"}
        assert body["success"] is True
        assert set(body["item"].keys()) == {"name", "quantity_before", "quantity_after"}
        assert body["item"] == {
            "name": "Milk",
            "quantity_before": 10.0,
            "quantity_after": 7.0,
        }
        inventory_broadcast.assert_awaited_once()
        assert inventory_broadcast.await_args.kwargs["action"] == "consumed"

    async def test_ambiguous_name_is_409_with_candidates(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        oat = await _product(db, "Oat milk")
        await _item(db, oat, "10")

        response = await client.post(
            "/api/ha/consume", json={"name": "milk", "amount": 1, "unit": "dl"}
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "ambiguous"
        (candidate,) = detail["candidates"]
        assert candidate["name"] == "Oat milk"

    async def test_insufficient_stock(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "2")

        response = await client.post(
            "/api/ha/consume", json={"name": "milk", "amount": 5, "unit": "dl"}
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "insufficient_stock"
        assert detail["available"] == 2.0

    async def test_not_found(self, client: AsyncClient, db: AsyncSession) -> None:
        response = await client.post(
            "/api/ha/consume", json={"name": "zyxxy", "amount": 1, "unit": "dl"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    async def test_idempotency_key_replays(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        inventory_broadcast, _ = broadcast
        milk = await _product(db, "Milk")
        await _item(db, milk, "10")
        headers = {"Idempotency-Key": "ha-consume-1"}
        body = {"name": "milk", "amount": 3, "unit": "dl"}

        first = await client.post("/api/ha/consume", json=body, headers=headers)
        second = await client.post("/api/ha/consume", json=body, headers=headers)

        assert (first.status_code, second.status_code) == (200, 200)
        assert second.json() == first.json()
        assert second.headers.get("Idempotent-Replayed") == "true"
        assert inventory_broadcast.await_count == 1
        assert await _count(db, IdempotencyKey) == 1

    async def test_same_key_different_body_is_conflict(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "10")
        headers = {"Idempotency-Key": "ha-consume-2"}
        await client.post(
            "/api/ha/consume",
            json={"name": "milk", "amount": 1, "unit": "dl"},
            headers=headers,
        )

        response = await client.post(
            "/api/ha/consume",
            json={"name": "milk", "amount": 2, "unit": "dl"},
            headers=headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "conflict"

    async def test_below_the_minimum_adds_one_open_item_and_broadcasts(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        milk = await _product(db, "Milk", min_stock_quantity=Decimal("10"))
        await _item(db, milk, "10")

        # `ha_consume` broadcasts this through `_broadcast_if_now_low`, which it shares
        # with the agent's own `/api/stock/consume` (it is defined, and imported, there) -
        # so the mock that catches it is `stock`'s, not `ha`'s own `broadcast` fixture.
        with patch(
            "app.api.endpoints.stock.broadcast_shopping_list_update",
            new_callable=AsyncMock,
        ) as shopping_broadcast:
            response = await client.post(
                "/api/ha/consume", json={"name": "milk", "amount": 6, "unit": "dl"}
            )

        assert response.status_code == 200, response.text
        rows = await _shopping_rows(db)
        assert len(rows) == 1
        [added] = rows
        assert (added.product_master_id, added.source) == (milk.id, "auto_restock")
        shopping_broadcast.assert_awaited_once()
        assert shopping_broadcast.await_args.kwargs["action"] == "created"

    async def test_a_second_consume_adds_nothing_more(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        milk = await _product(db, "Milk", min_stock_quantity=Decimal("10"))
        await _item(db, milk, "10")
        first = await client.post(
            "/api/ha/consume", json={"name": "milk", "amount": 6, "unit": "dl"}
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            "/api/ha/consume", json={"name": "milk", "amount": 1, "unit": "dl"}
        )

        assert second.status_code == 200, second.text
        assert len(await _shopping_rows(db)) == 1

    async def test_no_minimum_does_nothing(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "10")

        response = await client.post(
            "/api/ha/consume", json={"name": "milk", "amount": 6, "unit": "dl"}
        )

        assert response.status_code == 200, response.text
        assert await _shopping_rows(db) == []


async def _shopping_rows(db: AsyncSession) -> list[ShoppingListItem]:
    rows = await db.execute(
        select(ShoppingListItem).execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


class TestShoppingAdd:
    async def test_response_shape_defaults_and_broadcast(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        _, shopping_broadcast = broadcast

        response = await client.post("/api/ha/shopping/add", json={"name": "dish soap"})

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["name"] == "dish soap"
        assert body["quantity"] == 1.0
        assert body["unit"] == "pcs"
        assert body["priority"] == "normal"
        assert body["product_master_id"] is None
        assert body["is_purchased"] is False
        shopping_broadcast.assert_awaited_once()
        assert shopping_broadcast.await_args.kwargs["action"] == "created"

    async def test_f3_explicit_priority(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/ha/shopping/add", json={"name": "Milk", "priority": "urgent"}
        )

        assert response.status_code == 201, response.text
        assert response.json()["priority"] == "urgent"

    async def test_amount_and_unit(self, client: AsyncClient, db: AsyncSession) -> None:
        response = await client.post(
            "/api/ha/shopping/add", json={"name": "Milk", "amount": 2, "unit": "l"}
        )

        assert response.status_code == 201, response.text
        # Canonicalized on write (MVP-U1): "l" -> "dl", x10.
        assert (response.json()["quantity"], response.json()["unit"]) == (20.0, "dl")

    async def test_idempotency_key_replays(
        self, client: AsyncClient, db: AsyncSession, broadcast
    ) -> None:
        _, shopping_broadcast = broadcast
        headers = {"Idempotency-Key": "ha-shop-1"}
        body = {"name": "Milk"}

        first = await client.post("/api/ha/shopping/add", json=body, headers=headers)
        second = await client.post("/api/ha/shopping/add", json=body, headers=headers)

        assert (first.status_code, second.status_code) == (201, 201)
        assert second.json() == first.json()
        assert second.headers.get("Idempotent-Replayed") == "true"
        assert await _count(db, ShoppingListItem) == 1
        shopping_broadcast.assert_awaited_once()


class TestAuth:
    """AG1: the same bearer rules as every other /api route."""

    @pytest.mark.usefixtures("tokens")
    async def test_missing_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/ha/status")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "auth"

    @pytest.mark.usefixtures("tokens")
    async def test_read_token_can_get_status(self, client: AsyncClient) -> None:
        response = await client.get("/api/ha/status", headers=bearer(READ_SECRET))
        assert response.status_code == 200

    @pytest.mark.usefixtures("tokens")
    async def test_read_token_cannot_consume(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/ha/consume", json={}, headers=bearer(READ_SECRET)
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "auth"

    @pytest.mark.usefixtures("tokens")
    async def test_read_token_cannot_add_to_shopping_list(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/ha/shopping/add", json={}, headers=bearer(READ_SECRET)
        )
        assert response.status_code == 403
