"""Two corrected dates for one product at once must not deadlock (Q24).

Learning a shelf life locks the product and then every active item of it, to re-date the
`calculated` ones. A PATCH used to lock its own item first, and a quick add inserted its item
first (which holds a key-share lock on the product through the foreign key), so two siblings
corrected at the same moment - the iPad and an agent - each held what the other needed next.
PostgreSQL broke the tie by killing one of them, and the client got a 500.

Like `test_concurrent_writes.py`, these need their own committed sessions: the shared
`db_session` is one rolled-back transaction that no second connection can see.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.category import Category
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.inventory_item import InventoryItemUpdate, QuickAddRequest
from app.services.quick_add import quick_add
from app.services.shelf_life_learning import update_item

pytestmark = [pytest.mark.integration, pytest.mark.requires_db]

#: Rounds per test. One deadlock in any of them fails it; before the fix most rounds did.
ROUNDS = 10
TODAY = date.today()


@pytest.fixture
async def committed(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def tortillas(committed):
    """A product with four sealed, `calculated` items, committed, and removed afterwards."""
    suffix = uuid4().hex[:8]
    category_id = f"learn-{suffix}"

    async with committed() as session:
        session.add(
            Category(
                id=category_id,
                display_name=f"Learning {suffix}",
                default_shelf_life_days=7,
                sort_order=999,
            )
        )
        await session.flush()
        product = ProductMaster(
            canonical_name=f"Tortillas {suffix}",
            category=category_id,
            storage_type="pantry",
            default_shelf_life_days=7,
            shelf_life_source="model",
            unit_type="count",
            default_unit="pcs",
        )
        session.add(product)
        await session.flush()
        items = [
            InventoryItem(
                product_master_id=product.id,
                initial_quantity=Decimal(8),
                current_quantity=Decimal(8),
                unit="pcs",
                status="sealed",
                purchase_date=TODAY,
                expiry_date=TODAY + timedelta(days=7),
                expiry_source="calculated",
                location="pantry",
            )
            for _ in range(4)
        ]
        session.add_all(items)
        await session.commit()
        product_id = product.id
        item_ids = [item.id for item in items]

    yield product_id, item_ids

    async with committed() as session:
        ids = select(InventoryItem.id).where(
            InventoryItem.product_master_id == product_id
        )
        await session.execute(
            delete(ConsumptionLog).where(ConsumptionLog.inventory_item_id.in_(ids))
        )
        await session.execute(
            delete(InventoryItem).where(InventoryItem.product_master_id == product_id)
        )
        await session.execute(
            delete(ProductMaster).where(ProductMaster.id == product_id)
        )
        await session.execute(delete(Category).where(Category.id == category_id))
        await session.commit()


class TestTwoCorrectionsAtOnce:
    async def test_two_sibling_patches_both_land(self, committed, tortillas) -> None:
        _, (first, second, *_) = tortillas

        async def correct(item_id: UUID, days: int) -> None:
            async with committed() as session:
                result = await update_item(
                    session,
                    item_id,
                    InventoryItemUpdate(expiry_date=TODAY + timedelta(days=days)),
                )
                assert result.item is not None

        for round_ in range(ROUNDS):
            await asyncio.gather(
                correct(first, 30 + round_), correct(second, 60 + round_)
            )

        async with committed() as session:
            dates = [
                (await session.get(InventoryItem, item_id)).expiry_date  # type: ignore[union-attr]
                for item_id in (first, second)
            ]
        last = ROUNDS - 1
        assert dates == [
            TODAY + timedelta(days=30 + last),
            TODAY + timedelta(days=60 + last),
        ]

    async def test_two_dated_quick_adds_both_land(self, committed, tortillas) -> None:
        product_id, _ = tortillas

        async def add(days: int) -> None:
            async with committed() as session:
                await quick_add(
                    session,
                    QuickAddRequest(
                        product_id=product_id,
                        quantity=Decimal(8),
                        unit="pcs",
                        location="pantry",
                        purchase_date=TODAY,
                        expiry_date=TODAY + timedelta(days=days),
                    ),
                )

        for round_ in range(ROUNDS):
            await asyncio.gather(add(30 + round_), add(60 + round_))

        async with committed() as session:
            added = (
                await session.execute(
                    select(InventoryItem.id)
                    .where(InventoryItem.product_master_id == product_id)
                    .where(InventoryItem.expiry_source == "manual")
                )
            ).all()
        assert len(added) == 2 * ROUNDS
