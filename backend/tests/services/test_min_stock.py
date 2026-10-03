"""A1: auto-add to the shopping list once a consumption leaves a product short
(services/min_stock.py). Reuses AG6's "is it low" test and amount rule
(tests/services/test_shopping_generate.py), so this covers only what is new here: when it
fires once (not twice), when an open item already suppresses it, and that two
consumptions racing add exactly one item.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crud.inventory_item import apply_consumption, lock_active_items_for_product
from app.db.seed_categories import seed_categories
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem
from app.services import min_stock

TODAY = date.today()


@pytest.fixture
async def db(db_session: AsyncSession) -> AsyncSession:
    await seed_categories(db_session)
    await db_session.commit()
    return db_session


async def _product(
    db: AsyncSession,
    name: str,
    *,
    unit: str = "dl",
    min_stock: str | None = None,
    reorder: str | None = None,
) -> ProductMaster:
    unit_type = {"dl": "volume", "g": "weight", "pcs": "count"}[unit]
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type=unit_type,
        default_unit=unit,
        min_stock_quantity=Decimal(min_stock) if min_stock is not None else None,
        reorder_quantity=Decimal(reorder) if reorder is not None else None,
    )
    db.add(product)
    await db.commit()
    return product


async def _stock(
    db: AsyncSession,
    product: ProductMaster,
    quantity: str,
    *,
    unit: str = "dl",
    location: str = "main_fridge",
    status: str = "sealed",
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(quantity),
        current_quantity=Decimal(quantity),
        unit=unit,
        status=status,
        expiry_date=TODAY + timedelta(days=7),
        location=location,
    )
    db.add(item)
    await db.commit()
    return item


async def _open_item(
    db: AsyncSession,
    product: ProductMaster,
    quantity: str,
    *,
    unit: str = "dl",
    source: str = "manual",
) -> ShoppingListItem:
    item = ShoppingListItem(
        id=uuid4(),
        product_master_id=product.id,
        name=product.canonical_name,
        quantity=Decimal(quantity),
        unit=unit,
        priority="normal",
        source=source,
        is_purchased=False,
    )
    db.add(item)
    await db.commit()
    return item


async def _items(db: AsyncSession) -> list[ShoppingListItem]:
    rows = await db.execute(
        select(ShoppingListItem).execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _count(db: AsyncSession) -> int:
    return int(
        (await db.execute(select(func.count()).select_from(ShoppingListItem))).scalar()
    )


class TestWhenItDoesNothing:
    async def test_no_minimum_does_nothing(self, db) -> None:
        milk = await _product(db, "Milk")
        await _stock(db, milk, "0")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is None
        assert await _count(db) == 0

    async def test_at_the_minimum_does_nothing(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "10")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is None
        assert await _count(db) == 0

    async def test_above_the_minimum_does_nothing(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "12")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is None
        assert await _count(db) == 0

    async def test_an_open_manual_item_suppresses_it(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "2")
        await _open_item(db, milk, "5", source="manual")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is None
        assert await _count(db) == 1  # the manual item, untouched

    async def test_a_second_consume_adds_nothing_more(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "2")

        first = await min_stock.maybe_auto_add(db, milk)
        second = await min_stock.maybe_auto_add(db, milk)

        assert first is not None
        assert second is None
        assert await _count(db) == 1


class TestWhenItAdds:
    async def test_below_the_minimum_adds_the_shortfall(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is not None
        assert (added.product_master_id, added.name) == (milk.id, "Milk")
        assert (added.quantity, added.unit) == (Decimal("6"), "dl")
        assert (added.source, added.priority, added.is_purchased) == (
            "auto_restock",
            "normal",
            False,
        )
        [item] = await _items(db)
        assert item.id == added.id

    async def test_reorder_quantity_is_the_need_when_set(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10", reorder="20")
        await _stock(db, milk, "4")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is not None
        assert added.quantity == Decimal("20")

    async def test_no_stock_counts_as_zero(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "0", status="empty")
        await _stock(db, milk, "5", status="discarded")

        added = await min_stock.maybe_auto_add(db, milk)

        assert added is not None
        assert added.quantity == Decimal("10")

    async def test_stock_in_the_products_own_unit_is_counted(self, db) -> None:
        butter = await _product(db, "Butter", unit="g", min_stock="500")
        await _stock(db, butter, "200", unit="g")
        await _stock(db, butter, "50", unit="g", status="opened")

        added = await min_stock.maybe_auto_add(db, butter)

        assert added is not None
        assert (added.quantity, added.unit) == (Decimal("250"), "g")


class TestConcurrency:
    async def test_two_concurrent_consumptions_add_exactly_one_item(
        self, db_engine, committed_db_session: AsyncSession
    ) -> None:
        """Two sessions racing on different items of the same product: the advisory
        lock `maybe_auto_add` takes (AG6's own `GENERATE_LOCK`) serialises them, so
        whichever runs last sees the other's committed item and skips.

        ``committed_db_session`` is not used directly (every session here is its own,
        on its own connection, so two requests can really race) - it is taken only for
        its truncate-after cleanup, since this test's writes are real commits that the
        usual rolled-back ``db_session`` would not undo.
        """
        factory = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as setup:
            await seed_categories(setup)
            await setup.commit()
            milk = await _product(setup, "Milk", min_stock="15")
            await _stock(setup, milk, "10", location="main_fridge")
            await _stock(setup, milk, "10", location="pantry")

        real_on_hand = min_stock._on_hand

        async def slow_on_hand(session, product):
            result = await real_on_hand(session, product)
            # Both requests' own consume has already committed by the time either
            # reaches this read; the sleep widens the window so their advisory-lock
            # attempts actually overlap instead of running one after the other by luck.
            await asyncio.sleep(0.2)
            return result

        async def consume_and_check(location: str) -> ShoppingListItem | None:
            async with factory() as session:
                product = await session.get(ProductMaster, milk.id)
                [item] = await lock_active_items_for_product(
                    session, milk.id, location=location
                )
                apply_consumption(session, item, Decimal("9"))
                await session.commit()
                return await min_stock.maybe_auto_add(session, product)

        with patch("app.services.min_stock._on_hand", new=slow_on_hand):
            first, second = await asyncio.gather(
                consume_and_check("main_fridge"),
                consume_and_check("pantry"),
            )

        assert sorted([first is None, second is None]) == [False, True]
        async with factory() as check:
            assert await _count(check) == 1
