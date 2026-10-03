"""The run-out forecast over HTTP: `/api/stock/runout` (AG2) and `/api/ha/runout`.

The arithmetic itself is `tests/services/test_runout.py`'s job; this pins the two
routes' shapes, that `within_days` reaches the service, and that both sit behind the
same bearer auth as every other `/api` route (AG1).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_tokens import hash_secret
from app.core.config import settings
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services import runout

NOW = datetime.now(UTC)
TODAY = runout._today(NOW)

READ_SECRET = "runout-read-secret-01234567890"
WRITE_SECRET = "runout-write-secret-98765432100"


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
async def db(seeded_db: AsyncSession) -> AsyncSession:
    return seeded_db


async def _product(db: AsyncSession, name: str, *, unit: str = "dl") -> ProductMaster:
    unit_type = {"dl": "volume", "g": "weight", "pcs": "count"}[unit]
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type=unit_type,
        default_unit=unit,
    )
    db.add(product)
    await db.commit()
    return product


async def _item(
    db: AsyncSession, product: ProductMaster, quantity: str, *, unit: str = "dl"
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(quantity),
        current_quantity=Decimal(quantity),
        unit=unit,
        status="sealed",
        expiry_date=TODAY + timedelta(days=30),
        location="main_fridge",
    )
    db.add(item)
    await db.commit()
    return item


async def _log(
    db: AsyncSession,
    product: ProductMaster,
    *,
    days_ago: int,
    quantity: str,
    unit: str = "dl",
    action: str = "use_partial",
) -> None:
    log = ConsumptionLog(
        inventory_item_id=None,
        product_master_id=product.id,
        action=action,
        quantity_consumed=Decimal(quantity),
        quantity_after=Decimal("0"),
        unit=unit,
        batch_id=uuid4(),
        previous={},
        logged_at=NOW - timedelta(days=days_ago),
    )
    db.add(log)
    await db.commit()


async def _steady_milk(db: AsyncSession, *, stock: str = "5") -> ProductMaster:
    milk = await _product(db, "Milk")
    await _item(db, milk, stock)
    for days_ago in (8, 6, 4, 2, 0):
        await _log(db, milk, days_ago=days_ago, quantity="2")
    return milk


class TestStockRunout:
    async def test_response_shape(self, client: AsyncClient, db: AsyncSession) -> None:
        milk = await _steady_milk(db)

        response = await client.get("/api/stock/runout")

        assert response.status_code == 200, response.text
        (row,) = response.json()
        assert set(row.keys()) == {
            "product_id",
            "name",
            "unit",
            "active_stock",
            "daily_rate",
            "runs_out_on",
            "days_left",
            "expires_first",
            "status",
        }
        assert row["product_id"] == str(milk.id)
        assert row["name"] == "Milk"
        assert row["unit"] == "dl"
        assert row["status"] == "forecast"
        assert row["daily_rate"] == 1.25
        assert row["days_left"] == 4

    async def test_within_days_filters(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        soon = await _steady_milk(db, stock="2")  # ~2 days left
        far = await _product(db, "Later")
        await _item(db, far, "100")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, far, days_ago=days_ago, quantity="2")

        response = await client.get("/api/stock/runout", params={"within_days": 3})

        assert response.status_code == 200, response.text
        ids = {row["product_id"] for row in response.json()}
        assert str(soon.id) in ids
        assert str(far.id) not in ids

    async def test_insufficient_history(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        tea = await _product(db, "Tea")
        await _item(db, tea, "5")
        await _log(db, tea, days_ago=1, quantity="1")

        response = await client.get("/api/stock/runout")

        (row,) = [r for r in response.json() if r["product_id"] == str(tea.id)]
        assert row["status"] == "insufficient_history"
        assert row["daily_rate"] is None
        assert row["runs_out_on"] is None
        assert row["days_left"] is None

    async def test_writes_nothing(self, client: AsyncClient, db: AsyncSession) -> None:
        await _steady_milk(db)
        before = (await db.execute(ConsumptionLog.__table__.select())).all()

        await client.get("/api/stock/runout")

        after = (await db.execute(ConsumptionLog.__table__.select())).all()
        assert len(before) == len(after)

    async def test_excludes_out_by_default(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        out = await _product(db, "Gone")
        await _log(db, out, days_ago=0, quantity="1")

        response = await client.get("/api/stock/runout")

        ids = {row["product_id"] for row in response.json()}
        assert str(out.id) not in ids

    async def test_include_out_lists_it(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        out = await _product(db, "Gone")
        await _log(db, out, days_ago=0, quantity="1")

        response = await client.get("/api/stock/runout", params={"include_out": "true"})

        rows = {row["product_id"]: row for row in response.json()}
        assert rows[str(out.id)]["status"] == "out"


class TestStockRunoutAuth:
    @pytest.mark.usefixtures("tokens")
    async def test_missing_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/stock/runout")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "auth"

    @pytest.mark.usefixtures("tokens")
    async def test_read_token_is_enough(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        response = await client.get("/api/stock/runout", headers=bearer(READ_SECRET))
        assert response.status_code == 200


class TestHaRunout:
    async def test_response_shape(self, client: AsyncClient, db: AsyncSession) -> None:
        milk = await _steady_milk(db)

        response = await client.get("/api/ha/runout")

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {"items", "count", "out_count"}
        assert body["count"] == 1
        assert body["out_count"] == 0
        (item,) = body["items"]
        assert set(item.keys()) == {
            "id",
            "name",
            "unit",
            "days_left",
            "runs_out_on",
            "status",
        }
        assert item["id"] == str(milk.id)
        assert item["name"] == "Milk"
        assert item["days_left"] == 4
        assert item["status"] == "forecast"

    async def test_within_days_filters(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        soon = await _steady_milk(db, stock="2")
        far = await _product(db, "Later")
        await _item(db, far, "100")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, far, days_ago=days_ago, quantity="2")

        response = await client.get("/api/ha/runout", params={"within_days": 3})

        ids = {item["id"] for item in response.json()["items"]}
        assert str(soon.id) in ids
        assert str(far.id) not in ids

    async def test_agrees_with_the_agent_api(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        await _steady_milk(db)

        agent = (await client.get("/api/stock/runout")).json()
        ha = (await client.get("/api/ha/runout")).json()["items"]

        assert {(r["name"], r["days_left"], r["status"]) for r in agent} == {
            (r["name"], r["days_left"], r["status"]) for r in ha
        }

    async def test_excludes_out_but_counts_it(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        await _steady_milk(db)
        out = await _product(db, "Gone")
        await _log(db, out, days_ago=0, quantity="1")

        response = await client.get("/api/ha/runout")

        body = response.json()
        ids = {item["id"] for item in body["items"]}
        assert str(out.id) not in ids
        assert body["out_count"] == 1
        assert body["count"] == 1

    async def test_include_out_lists_it_and_still_counts_it(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        await _steady_milk(db)
        out = await _product(db, "Gone")
        await _log(db, out, days_ago=0, quantity="1")

        response = await client.get("/api/ha/runout", params={"include_out": "true"})

        body = response.json()
        ids = {item["id"] for item in body["items"]}
        assert str(out.id) in ids
        assert body["out_count"] == 1
        assert body["count"] == 2

    async def test_production_shape_default_holds_only_the_forecast(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        """28 products already out, one real forecast within 7 days (the live
        finding): the default list holds exactly the forecast, with out_count 28."""
        for i in range(28):
            out = await _product(db, f"Out {i}")
            await _log(db, out, days_ago=0, quantity="1")

        forecast = await _steady_milk(db, stock="9")  # 9 dl / 1.25 dl/day = 7 days left

        response = await client.get("/api/ha/runout", params={"within_days": 7})

        body = response.json()
        assert body["count"] == 1
        assert body["items"][0]["id"] == str(forecast.id)
        assert body["out_count"] == 28

        full = await client.get(
            "/api/ha/runout", params={"within_days": 7, "include_out": "true"}
        )
        assert full.json()["count"] == 29
        assert full.json()["out_count"] == 28


class TestHaRunoutAuth:
    @pytest.mark.usefixtures("tokens")
    async def test_missing_token_is_401(self, client: AsyncClient) -> None:
        response = await client.get("/api/ha/runout")
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "auth"

    @pytest.mark.usefixtures("tokens")
    async def test_read_token_is_enough(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        response = await client.get("/api/ha/runout", headers=bearer(READ_SECRET))
        assert response.status_code == 200
