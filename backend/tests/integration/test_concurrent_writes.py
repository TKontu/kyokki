"""Two hands on the same item at once (H23, H42).

`docs/reviews/pipeline-foundations.md` found this on 2026-09-17: *"Two overlapping consumes of
one item (iPad and a phone, or the agent track later) both read 4 and both write 3; one
consumption is lost while both `consumption_log` rows land."* The fix is a row lock inside
`consume_inventory_item`, and a lock is the kind of thing that can be present and wrong, so it
needs a test that fails without it.

`docs/TODO.md` H42 asks for exactly these and there were none in `backend/tests` - the two
existing "race" tests simulate an ordering within one session rather than contending.

**These cannot use the shared `db_session`.** Every other test runs inside one transaction that
is rolled back, so nothing it writes is visible from another connection - which is precisely
what this needs. Setup, contention and assertions all go through their own committed sessions,
and the rows are cleaned up at the end.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crud.inventory_item import consume_inventory_item
from app.crud.shopping_list_item import shopping_list_item as crud_shopping
from app.models.category import Category
from app.models.consumption_log import ConsumptionLog
from app.models.idempotency_key import IdempotencyKey
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem
from app.services import shopping_generate

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]


@pytest.fixture
async def committed(db_engine):
    """A session factory whose writes other connections can actually see."""
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def stocked_item(committed):
    """Ten decilitres of something, committed, and taken away again afterwards."""
    suffix = uuid4().hex[:8]
    category_id = f"conc-{suffix}"

    async with committed() as session:
        session.add(
            Category(
                id=category_id,
                display_name=f"Concurrency {suffix}",
                default_shelf_life_days=14,
                sort_order=999,
            )
        )
        await session.flush()
        product = ProductMaster(
            canonical_name=f"Sour cream {suffix}",
            category=category_id,
            storage_type="refrigerator",
            default_shelf_life_days=14,
            unit_type="volume",
            default_unit="dl",
        )
        session.add(product)
        await session.flush()
        item = InventoryItem(
            product_master_id=product.id,
            initial_quantity=Decimal(10),
            current_quantity=Decimal(10),
            unit="dl",
            status="sealed",
            purchase_date=date.today(),
            expiry_date=date.today() + timedelta(days=14),
            expiry_source="calculated",
            location="main_fridge",
        )
        session.add(item)
        await session.commit()
        item_id, product_id = item.id, product.id

    yield item_id

    async with committed() as session:
        await session.execute(
            delete(ConsumptionLog).where(ConsumptionLog.inventory_item_id == item_id)
        )
        await session.execute(delete(InventoryItem).where(InventoryItem.id == item_id))
        await session.execute(
            delete(ProductMaster).where(ProductMaster.id == product_id)
        )
        await session.execute(delete(Category).where(Category.id == category_id))
        await session.commit()


async def _logs(committed, item_id) -> list[ConsumptionLog]:
    async with committed() as session:
        result = await session.execute(
            select(ConsumptionLog).where(ConsumptionLog.inventory_item_id == item_id)
        )
        return list(result.scalars().all())


async def _remaining(committed, item_id) -> Decimal:
    async with committed() as session:
        item = await session.get(InventoryItem, item_id)
        assert item is not None
        return Decimal(str(item.current_quantity))


class TestTwoConsumesAtOnce:
    async def test_neither_helping_is_lost(self, committed, stocked_item) -> None:
        """Both amounts come off, and the log agrees with the quantity.

        Without the lock both callers read 10, both compute their own 10 - n, and the row ends
        at whichever committed last - with two log rows for helpings that never left the fridge.
        """

        async def consume(amount: int) -> None:
            async with committed() as session:
                await consume_inventory_item(session, stocked_item, Decimal(amount))

        await asyncio.gather(consume(2), consume(3))

        assert await _remaining(committed, stocked_item) == Decimal("5.00")
        assert sorted(
            log.quantity_consumed for log in await _logs(committed, stocked_item)
        ) == [
            Decimal("2.00"),
            Decimal("3.00"),
        ]

    async def test_the_second_one_is_refused_rather_than_overdrawing(
        self, committed, stocked_item
    ) -> None:
        """Two callers each wanting more than half cannot both win.

        The loser's budget check runs against the committed amount, which is the check doing
        its job rather than a failure - and it writes no log row.
        """

        async def consume(amount: int) -> str:
            async with committed() as session:
                try:
                    await consume_inventory_item(session, stocked_item, Decimal(amount))
                except ValueError:
                    return "refused"
                return "consumed"

        results = await asyncio.gather(consume(7), consume(7))

        assert sorted(results) == ["consumed", "refused"]
        assert await _remaining(committed, stocked_item) == Decimal("3.00")
        assert len(await _logs(committed, stocked_item)) == 1


@pytest.fixture
async def low_products(committed):
    """Three products below their minimum, with no stock at all; removed afterwards."""
    suffix = uuid4().hex[:8]
    category_id = f"conc-{suffix}"

    async with committed() as session:
        session.add(
            Category(
                id=category_id,
                display_name=f"Concurrency {suffix}",
                default_shelf_life_days=14,
                sort_order=999,
            )
        )
        await session.flush()
        products = [
            ProductMaster(
                canonical_name=f"{name} {suffix}",
                category=category_id,
                storage_type="refrigerator",
                default_shelf_life_days=14,
                unit_type="volume",
                default_unit="dl",
                min_stock_quantity=Decimal(5),
            )
            for name in ("Milk", "Cream", "Yoghurt")
        ]
        session.add_all(products)
        await session.commit()
        product_ids = [product.id for product in products]

    yield product_ids

    async with committed() as session:
        await session.execute(
            delete(ShoppingListItem).where(
                ShoppingListItem.product_master_id.in_(product_ids)
            )
        )
        await session.execute(
            delete(ProductMaster).where(ProductMaster.id.in_(product_ids))
        )
        await session.execute(delete(Category).where(Category.id == category_id))
        await session.commit()


class TestTwoGeneratesAtOnce:
    async def test_the_second_sees_the_first_s_items(
        self, committed, low_products
    ) -> None:
        """AG6 review: two generates without a shared key both inserted (3 low -> 5 items).

        Reading the open items is slowed down so both callers are sure to overlap; the
        advisory lock makes the second wait for the first's commit and then find its items.
        """
        real_get_by_product = crud_shopping.get_by_product

        async def slow_get_by_product(db, *, product_master_id):
            items = await real_get_by_product(db, product_master_id=product_master_id)
            await asyncio.sleep(0.05)
            return items

        async def generate() -> None:
            async with committed() as session:
                await shopping_generate.generate(session, ["low_stock"], dry_run=False)

        with patch.object(
            crud_shopping, "get_by_product", side_effect=slow_get_by_product
        ):
            await asyncio.gather(generate(), generate())

        async with committed() as session:
            items = (
                (
                    await session.execute(
                        select(ShoppingListItem).where(
                            ShoppingListItem.product_master_id.in_(low_products)
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert sorted(item.product_master_id for item in items) == sorted(low_products)


@pytest.fixture
async def own_requests(committed):
    """A client whose every request gets its own session and connection, committing for
    real, with the shopping broadcast mocked. Rows made under the test's keys go after."""
    from app.db.session import get_db
    from app.main import app

    async def override_get_db():
        async with committed() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch(
            "app.api.endpoints.shopping.broadcast_shopping_list_update",
            new_callable=AsyncMock,
        ) as broadcast:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client, broadcast
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def race_names(committed):
    """A unique item name and key prefix; their rows are deleted afterwards."""
    suffix = uuid4().hex[:8]
    yield f"Race item {suffix}", f"race-{suffix}"

    async with committed() as session:
        await session.execute(
            delete(ShoppingListItem).where(
                ShoppingListItem.name == f"Race item {suffix}"
            )
        )
        await session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.key.like(f"race-{suffix}%"))
        )
        await session.commit()


def _slow(real):
    """The CRUD write, then a pause before the answer is remembered: a retry that
    arrives now finds the item committed and no key stored yet."""

    async def slow(db: AsyncSession, **kwargs):
        result = await real(db, **kwargs)
        await asyncio.sleep(0.3)
        return result

    return slow


class TestTwoShoppingRetriesAtOnce:
    """AG6 follow-up: a client that times out and retries while its first request still
    runs. `idempotency.held` makes the retry wait for the stored answer and replay it."""

    async def test_two_creates_with_one_key_make_one_item(
        self, committed, own_requests, race_names
    ) -> None:
        client, broadcast = own_requests
        name, key = race_names
        body = {"name": name, "quantity": 2, "unit": "pcs"}
        headers = {"Idempotency-Key": f"{key}-create"}

        with patch.object(
            crud_shopping, "create", side_effect=_slow(crud_shopping.create)
        ):
            first, second = await asyncio.gather(
                client.post("/api/shopping/", json=body, headers=headers),
                client.post("/api/shopping/", json=body, headers=headers),
            )

        assert (first.status_code, second.status_code) == (201, 201)
        assert first.json() == second.json()
        replayed = [
            r.headers.get("Idempotent-Replayed") == "true" for r in (first, second)
        ]
        assert sorted(replayed) == [False, True]
        async with committed() as session:
            items = (
                (
                    await session.execute(
                        select(ShoppingListItem).where(ShoppingListItem.name == name)
                    )
                )
                .scalars()
                .all()
            )
        assert len(items) == 1
        assert broadcast.await_count == 1

    async def test_two_purchases_with_one_key_run_once(
        self, committed, own_requests, race_names
    ) -> None:
        client, broadcast = own_requests
        name, key = race_names
        async with committed() as session:
            item = ShoppingListItem(
                name=name,
                quantity=Decimal(2),
                unit="pcs",
                priority="normal",
                source="manual",
                is_purchased=False,
            )
            session.add(item)
            await session.commit()
            item_id = item.id
        url = f"/api/shopping/{item_id}/purchase"
        headers = {"Idempotency-Key": f"{key}-buy"}

        with patch.object(
            crud_shopping,
            "mark_purchased",
            side_effect=_slow(crud_shopping.mark_purchased),
        ):
            first, second = await asyncio.gather(
                client.post(url, headers=headers),
                client.post(url, headers=headers),
            )

        assert (first.status_code, second.status_code) == (200, 200)
        # One purchase ran: the replay carries the same purchased_at
        assert first.json() == second.json()
        replayed = [
            r.headers.get("Idempotent-Replayed") == "true" for r in (first, second)
        ]
        assert sorted(replayed) == [False, True]
        assert broadcast.await_count == 1
