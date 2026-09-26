"""AG2: the agent-facing stock routes - /api/stock, /api/stock/add, /api/stock/consume."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import AgentError
from app.models.consumption_log import ConsumptionLog
from app.models.idempotency_key import IdempotencyKey
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.store_product_alias import StoreProductAlias
from app.services import stock as stock_service

TODAY = date.today()


@pytest.fixture(autouse=True)
def broadcast():
    with patch(
        "app.api.endpoints.stock.broadcast_inventory_update", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
async def own_sessions(db_engine, committed_db_session: AsyncSession):
    """Every request gets a session of its own on its own connection, committing for real.

    The savepoint ``db_session`` runs every request on one connection, so it cannot show
    two requests racing each other. ``committed_db_session`` truncates afterwards.
    """
    from app.db.seed_categories import seed_categories
    from app.db.session import get_db
    from app.main import app

    await seed_categories(committed_db_session)
    await committed_db_session.commit()
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield committed_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


def _id(obj):
    """The row's id without loading it: a rolled-back session has expired every object."""
    return inspect(obj).identity[0]


async def _product(
    db: AsyncSession, name: str, *, unit: str = "dl", category: str = "dairy"
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
    unit: str = "dl",
    expires_in: int = 7,
    location: str = "main_fridge",
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(quantity),
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
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def _quantity(db: AsyncSession, item: InventoryItem) -> Decimal:
    found = await db.get(InventoryItem, _id(item), populate_existing=True)
    assert found is not None
    return Decimal(str(found.current_quantity))


class TestTheErrorShape:
    def test_detail_carries_a_stable_code(self) -> None:
        error = AgentError("ambiguous", "Which one?", candidates=[{"name": "x"}])

        assert error.status_code == 409
        assert error.detail == {
            "code": "ambiguous",
            "message": "Which one?",
            "candidates": [{"name": "x"}],
        }

    @pytest.mark.parametrize(
        ("code", "status"),
        [
            ("not_found", 404),
            ("ambiguous", 409),
            ("insufficient_stock", 409),
            ("invalid", 400),
            ("conflict", 409),
        ],
    )
    def test_each_code_has_its_status(self, code: str, status: int) -> None:
        assert AgentError(code, "m").status_code == status

    def test_hint_and_extras_are_included_when_given(self) -> None:
        error = AgentError(
            "insufficient_stock", "Short", available=Decimal("3"), unit="dl"
        )

        assert error.detail == {
            "code": "insufficient_stock",
            "message": "Short",
            "available": 3.0,
            "unit": "dl",
        }
        assert AgentError("not_found", "m", hint="h").detail["hint"] == "h"


class TestStockList:
    async def test_one_row_per_product(self, client: AsyncClient, seeded_db) -> None:
        milk = await _product(seeded_db, "Milk")
        await _item(seeded_db, milk, "5", expires_in=2)
        await _item(seeded_db, milk, "10", expires_in=6, location="pantry")

        response = await client.get("/api/stock")

        assert response.status_code == 200
        (row,) = response.json()
        assert row == {
            "product_id": str(_id(milk)),
            "product_name": "Milk",
            "category": "dairy",
            "category_icon": row["category_icon"],
            "unit": "dl",
            "total": 15.0,
            "item_count": 2,
            "earliest_expiry": str(TODAY + timedelta(days=2)),
            "locations": {"main_fridge": 5.0, "pantry": 10.0},
            "expiring": True,
        }

    async def test_q_finds_learned_and_printed_names(
        self, client: AsyncClient, seeded_db
    ) -> None:
        mince = await _product(seeded_db, "Ground beef", unit="g", category="meat")
        milk = await _product(seeded_db, "Milk")
        seeded_db.add(
            ProductName(product_master_id=_id(mince), name="jauheliha", source="cook")
        )
        seeded_db.add(
            StoreProductAlias(
                product_master_id=_id(milk),
                store_chain="s-market",
                receipt_name="VALIO KEVYTMAITO 1L",
            )
        )
        await seeded_db.commit()
        await _item(seeded_db, mince, "400", unit="g")
        await _item(seeded_db, milk, "10")

        learned = (await client.get("/api/stock", params={"q": "jauhe"})).json()
        printed = (await client.get("/api/stock", params={"q": "kevytmaito"})).json()

        assert [r["product_id"] for r in learned] == [str(_id(mince))]
        assert [r["product_id"] for r in printed] == [str(_id(milk))]

    async def test_an_unknown_location_is_a_422(
        self, client: AsyncClient, seeded_db
    ) -> None:
        response = await client.get("/api/stock", params={"location": "garage"})

        assert response.status_code == 422


class TestStockAdd:
    async def test_adds_and_says_whether_the_product_is_new(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        response = await client.post(
            "/api/stock/add",
            json={"name": "Peas", "category": "frozen", "quantity": 500, "unit": "g"},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["product_created"] is True
        assert body["item"]["product_name"] == "Peas"
        assert (body["item"]["current_quantity"], body["item"]["unit"]) == (500, "g")
        broadcast.assert_awaited_once()
        assert broadcast.await_args.kwargs["action"] == "created"

    async def test_an_unknown_product_id_is_invalid(
        self, client: AsyncClient, seeded_db
    ) -> None:
        response = await client.post(
            "/api/stock/add", json={"product_id": str(uuid4()), "quantity": 1}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid"

    async def test_a_repeated_key_replays_without_a_second_item(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        body = {"name": "Peas", "category": "frozen", "quantity": 500, "unit": "g"}
        headers = {"Idempotency-Key": "add-1"}

        first = await client.post("/api/stock/add", json=body, headers=headers)
        second = await client.post("/api/stock/add", json=body, headers=headers)

        assert (first.status_code, second.status_code) == (201, 201)
        assert second.json() == first.json()
        assert await _count(seeded_db, InventoryItem) == 1
        assert broadcast.await_count == 1

    async def test_the_same_key_with_another_body_is_a_conflict(
        self, client: AsyncClient, seeded_db
    ) -> None:
        headers = {"Idempotency-Key": "add-2"}
        body = {"name": "Peas", "category": "frozen", "quantity": 500, "unit": "g"}
        await client.post("/api/stock/add", json=body, headers=headers)

        response = await client.post(
            "/api/stock/add", json={**body, "quantity": 300}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "conflict"
        assert await _count(seeded_db, InventoryItem) == 1

    async def test_an_equal_body_spelled_differently_replays(
        self, client: AsyncClient, seeded_db
    ) -> None:
        headers = {"Idempotency-Key": "add-3"}
        body = {"name": "Peas", "category": "frozen", "quantity": 500, "unit": "g"}
        first = await client.post("/api/stock/add", json=body, headers=headers)

        # 500.0 for 500, and a default sent explicitly: the same request
        second = await client.post(
            "/api/stock/add",
            json={**body, "quantity": 500.0, "location": None},
            headers=headers,
        )

        assert (first.status_code, second.status_code) == (201, 201)
        assert second.json() == first.json()
        assert await _count(seeded_db, InventoryItem) == 1

    async def test_no_key_means_two_items(self, client: AsyncClient, seeded_db) -> None:
        body = {"name": "Peas", "category": "frozen", "quantity": 500, "unit": "g"}

        await client.post("/api/stock/add", json=body)
        await client.post("/api/stock/add", json=body)

        assert await _count(seeded_db, InventoryItem) == 2


class TestStockAddRace:
    async def test_two_concurrent_adds_with_one_key_make_one_item(
        self, client: AsyncClient, own_sessions: AsyncSession, broadcast
    ) -> None:
        """A client that times out and retries while its first request still runs."""
        real_quick_add = stock_service.quick_add

        async def slow_quick_add(db, request):
            result = await real_quick_add(db, request)
            # Quick add has committed; its answer is not remembered yet.
            await asyncio.sleep(0.3)
            return result

        body = {"name": "Peas", "category": "frozen", "quantity": 500, "unit": "g"}
        headers = {"Idempotency-Key": "add-race"}
        with patch("app.services.stock.quick_add", new=slow_quick_add):
            first, second = await asyncio.gather(
                client.post("/api/stock/add", json=body, headers=headers),
                client.post("/api/stock/add", json=body, headers=headers),
            )

        assert (first.status_code, second.status_code) == (201, 201)
        assert second.json() == first.json()
        assert await _count(own_sessions, InventoryItem) == 1
        assert await _count(own_sessions, IdempotencyKey) == 1
        assert broadcast.await_count == 1


URL = "/api/stock/consume"


class TestStockConsume:
    async def test_fifo_by_name(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        sooner = await _item(seeded_db, milk, "5", expires_in=2)
        later = await _item(seeded_db, milk, "10", expires_in=6)

        response = await client.post(
            URL, json={"product": "milk", "amount": 7, "unit": "dl"}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["product_id"] == str(_id(milk))
        assert body["product_name"] == "Milk"
        assert body["requested"] == {"amount": 7.0, "unit": "dl"}
        assert body["consumed"] == [
            {
                "item_id": str(_id(sooner)),
                "amount": 5.0,
                "unit": "dl",
                "remaining": 0.0,
                "status": "empty",
            },
            {
                "item_id": str(_id(later)),
                "amount": 2.0,
                "unit": "dl",
                "remaining": 8.0,
                "status": body["consumed"][1]["status"],
            },
        ]
        assert (body["remaining_total"], body["unit"], body["dry_run"]) == (
            8.0,
            "dl",
            False,
        )
        assert {c.kwargs["inventory_item_id"] for c in broadcast.await_args_list} == {
            _id(sooner),
            _id(later),
        }
        # The same action the iPad's single-item consume broadcasts.
        assert {c.kwargs["action"] for c in broadcast.await_args_list} == {"consumed"}

    async def test_litres_against_decilitres(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "10")

        response = await client.post(
            URL, json={"product": "Milk", "amount": 0.5, "unit": "l"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["consumed"][0]["amount"] == 5.0
        assert await _quantity(seeded_db, item) == Decimal("5")

    async def test_grams_against_pieces_is_invalid(
        self, client: AsyncClient, seeded_db
    ) -> None:
        apples = await _product(seeded_db, "Apple", unit="pcs", category="fruits")
        await _item(seeded_db, apples, "6", unit="pcs")

        response = await client.post(
            URL, json={"product": "apple", "amount": 200, "unit": "g"}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "invalid"

    async def test_short_stock(self, client: AsyncClient, seeded_db, broadcast) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "5")

        response = await client.post(
            URL, json={"product": "milk", "amount": 8, "unit": "dl"}
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert (detail["code"], detail["available"], detail["unit"]) == (
            "insufficient_stock",
            5.0,
            "dl",
        )
        assert await _quantity(seeded_db, item) == Decimal("5")
        broadcast.assert_not_awaited()

    async def test_allow_partial(self, client: AsyncClient, seeded_db) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "5")

        response = await client.post(
            URL,
            json={"product": "milk", "amount": 8, "unit": "dl", "allow_partial": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["consumed"][0]["amount"] == 5.0
        assert await _quantity(seeded_db, item) == Decimal("0")

    async def test_dry_run(self, client: AsyncClient, seeded_db, broadcast) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "5")

        response = await client.post(
            URL,
            json={"product": "milk", "amount": 2, "unit": "dl", "dry_run": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["dry_run"] is True
        assert response.json()["consumed"][0]["remaining"] == 3.0
        assert await _quantity(seeded_db, item) == Decimal("5")
        assert await _count(seeded_db, ConsumptionLog) == 0
        broadcast.assert_not_awaited()

    async def test_a_near_miss_is_ambiguous(
        self, client: AsyncClient, seeded_db
    ) -> None:
        oat = await _product(seeded_db, "Oat milk")
        await _item(seeded_db, oat, "10")

        response = await client.post(
            URL, json={"product": "milk", "amount": 1, "unit": "dl"}
        )

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "ambiguous"
        (candidate,) = detail["candidates"]
        assert candidate["product_id"] == str(_id(oat))
        assert candidate["name"] == "Oat milk"
        assert candidate["source"] == "canonical"
        assert 0 < candidate["score"] <= 1

    async def test_nothing_like_it(self, client: AsyncClient, seeded_db) -> None:
        response = await client.post(
            URL, json={"product": "zyxxy", "amount": 1, "unit": "dl"}
        )

        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["code"] == "not_found"
        assert "POST /api/stock/add" in detail["hint"]

    async def test_an_unknown_product_id(self, client: AsyncClient, seeded_db) -> None:
        response = await client.post(
            URL, json={"product_id": str(uuid4()), "amount": 1, "unit": "dl"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    async def test_product_and_product_id_together_is_a_422(
        self, client: AsyncClient, seeded_db
    ) -> None:
        response = await client.post(
            URL,
            json={
                "product": "milk",
                "product_id": str(uuid4()),
                "amount": 1,
                "unit": "dl",
            },
        )

        assert response.status_code == 422

    async def test_a_repeated_key_replays_without_a_second_consume(
        self, client: AsyncClient, seeded_db, broadcast
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "10")
        body = {"product": "milk", "amount": 2, "unit": "dl"}
        headers = {"Idempotency-Key": "consume-1"}

        first = await client.post(URL, json=body, headers=headers)
        second = await client.post(URL, json=body, headers=headers)

        assert (first.status_code, second.status_code) == (200, 200)
        assert second.json() == first.json()
        assert await _quantity(seeded_db, item) == Decimal("8")
        assert await _count(seeded_db, ConsumptionLog) == 1
        assert broadcast.await_count == 1

    async def test_the_same_key_with_another_body_is_a_conflict(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "10")
        headers = {"Idempotency-Key": "consume-2"}
        await client.post(
            URL, json={"product": "milk", "amount": 2, "unit": "dl"}, headers=headers
        )

        response = await client.post(
            URL, json={"product": "milk", "amount": 3, "unit": "dl"}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "conflict"
        assert await _quantity(seeded_db, item) == Decimal("8")

    async def test_an_equal_body_spelled_differently_replays(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "10")
        headers = {"Idempotency-Key": "consume-4"}
        first = await client.post(
            URL, json={"product": "milk", "amount": 2, "unit": "dl"}, headers=headers
        )

        second = await client.post(
            URL,
            json={
                "product": "milk",
                "amount": 2.0,
                "unit": "dl",
                "allow_partial": False,
            },
            headers=headers,
        )

        assert (first.status_code, second.status_code) == (200, 200)
        assert second.json() == first.json()
        assert await _quantity(seeded_db, item) == Decimal("8")

    async def test_a_dry_run_is_not_remembered(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        item = await _item(seeded_db, milk, "10")
        headers = {"Idempotency-Key": "consume-3"}

        await client.post(
            URL,
            json={"product": "milk", "amount": 2, "unit": "dl", "dry_run": True},
            headers=headers,
        )
        real = await client.post(
            URL, json={"product": "milk", "amount": 2, "unit": "dl"}, headers=headers
        )

        assert real.status_code == 200
        assert real.json()["dry_run"] is False
        assert await _quantity(seeded_db, item) == Decimal("8")

    async def test_undo_reverses_one_item_of_a_multi_item_consume(
        self, client: AsyncClient, seeded_db
    ) -> None:
        milk = await _product(seeded_db, "Milk")
        sooner = await _item(seeded_db, milk, "5", expires_in=2)
        later = await _item(seeded_db, milk, "10", expires_in=6)
        await client.post(URL, json={"product": "milk", "amount": 7, "unit": "dl"})

        preview = (await client.get("/api/inventory/undo")).json()
        undone = await client.post(
            "/api/inventory/undo", json={"batch_id": preview["batch_id"]}
        )

        assert undone.status_code == 200, undone.text
        assert len(preview["steps"]) == 1
        restored = {
            await _quantity(seeded_db, sooner),
            await _quantity(seeded_db, later),
        }
        assert restored in ({Decimal("5"), Decimal("8")}, {Decimal("0"), Decimal("10")})
