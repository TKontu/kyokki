"""Home Assistant REST endpoints: the shapes and logic in services/ha.py.

Thin over what already exists (AG2's stock-by-name, AG6's low_stock, and the crud
`expiring_days` rule), so these tests pin the shaping, not the underlying behaviour
that services/stock.py and services/shopping_generate.py already cover.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import inventory_item as crud_inventory
from app.db.seed_categories import seed_categories
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.services import ha
from app.services.product_lookup import AmbiguousProduct, ProductNotFound
from app.services.stock import InsufficientStock

TODAY = date.today()


@pytest.fixture
async def db(db_session: AsyncSession) -> AsyncSession:
    await seed_categories(db_session)
    await db_session.commit()
    return db_session


def _id(obj):
    """The row's id without loading it: a rolled-back session has expired every object."""
    return inspect(obj).identity[0]


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


class TestStatus:
    async def test_counts_active_items_only(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", expires_in=1, location="main_fridge")
        await _item(db, milk, "3", expires_in=10, location="freezer")
        expired_item = await _item(db, milk, "1", expires_in=-2, location="pantry")
        gone = await _item(db, milk, "2", expires_in=5)
        gone.status = "discarded"
        await db.commit()

        result = await ha.status(db)

        assert result.total_items == 3
        assert result.expired == 1
        assert result.expiring_within_3_days == 2  # the 1-day item and the expired one
        assert result.by_location == {
            "main_fridge": 1,
            "freezer": 1,
            "pantry": 1,
        }
        assert result.last_updated is not None
        del expired_item

    async def test_empty_kitchen(self, db: AsyncSession) -> None:
        result = await ha.status(db)
        assert (result.total_items, result.expired, result.expiring_within_3_days) == (
            0,
            0,
            0,
        )
        assert result.by_location == {}


class TestExpiring:
    async def test_shapes_and_sorts_soonest_first(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        later = await _item(db, milk, "5", initial="10", expires_in=2)
        sooner = await _item(db, milk, "2", initial="4", expires_in=1)

        result = await ha.expiring(db, days=3)

        assert [item.id for item in result.items] == [_id(sooner), _id(later)]
        first = result.items[0]
        assert first.name == "Milk"
        assert first.category == "dairy"
        assert first.expiry_date == TODAY + timedelta(days=1)
        assert first.days_until_expiry == 1
        assert first.quantity_percent == 50

    async def test_days_until_expiry_is_negative_once_past(
        self, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "1", expires_in=-2)

        result = await ha.expiring(db, days=-1)

        assert result.count == 1
        assert result.items[0].days_until_expiry == -2

    async def test_limit_truncates(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        for day in range(5):
            await _item(db, milk, "1", expires_in=day)

        result = await ha.expiring(db, days=10, limit=2)

        assert result.count == 2
        assert len(result.items) == 2

    async def test_pinned_against_the_shared_expired_rule(
        self, db: AsyncSession
    ) -> None:
        """ "Expired" is `expiring_days=-1` in `crud.get_inventory_items` - the same rule
        the iPad's expired shelf and the agent API use. `expiring(days=-1)` must return
        exactly the ids that calling the crud function directly returns, not a restated
        version of the same date arithmetic."""
        milk = await _product(db, "Milk")
        await _item(db, milk, "1", expires_in=-5)
        await _item(db, milk, "1", expires_in=0)  # due today: not yet expired
        await _item(db, milk, "1", expires_in=-1)

        result = await ha.expiring(db, days=-1, limit=100)

        direct = await crud_inventory.get_inventory_items(db, expiring_days=-1)
        assert {item.id for item in result.items} == {item.id for item in direct}
        assert result.count == len(direct) == 2


class TestLowStock:
    async def test_below_min_stock_is_listed(self, db: AsyncSession) -> None:
        low = await _product(
            db,
            "Eggs",
            category="dairy",
            min_stock_quantity=Decimal("10"),
            reorder_quantity=Decimal("12"),
        )
        await _item(db, low, "4", unit="dl")
        fine = await _product(
            db, "Butter", min_stock_quantity=Decimal("2"), reorder_quantity=Decimal("2")
        )
        await _item(db, fine, "5", unit="dl")

        result = await ha.low_stock(db)

        assert result.count == 1
        item = result.items[0]
        assert item.id == _id(low)
        assert item.name == "Eggs"
        assert item.category == "dairy"
        assert item.quantity_percent == 40  # 4 / 10
        assert item.on_shopping_list is False

    async def test_writes_nothing(self, db: AsyncSession) -> None:
        from sqlalchemy import func, select

        from app.models.shopping_list_item import ShoppingListItem

        low = await _product(
            db, "Eggs", min_stock_quantity=Decimal("10"), reorder_quantity=Decimal("12")
        )
        await _item(db, low, "4", unit="dl")

        await ha.low_stock(db)

        count = (
            await db.execute(select(func.count()).select_from(ShoppingListItem))
        ).scalar_one()
        assert count == 0

    async def test_no_products_need_restocking(self, db: AsyncSession) -> None:
        result = await ha.low_stock(db)
        assert (result.items, result.count) == ([], 0)


class TestConsumeByName:
    async def test_consumes_and_shapes_before_and_after(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "10")

        response, result = await ha.consume_by_name(db, "milk", Decimal("3"), "dl")

        assert response.success is True
        assert response.item.name == "Milk"
        assert response.item.quantity_before == Decimal("10")
        assert response.item.quantity_after == Decimal("7")
        assert result.product_name == "Milk"
        assert len(result.consumed) == 1

    async def test_ambiguous_name_raises(self, db: AsyncSession) -> None:
        oat = await _product(db, "Oat milk")
        await _item(db, oat, "10")

        with pytest.raises(AmbiguousProduct):
            await ha.consume_by_name(db, "milk", Decimal("1"), "dl")

    async def test_unknown_name_raises(self, db: AsyncSession) -> None:
        with pytest.raises(ProductNotFound):
            await ha.consume_by_name(db, "zyxxy", Decimal("1"), "dl")

    async def test_insufficient_stock_raises(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "2")

        with pytest.raises(InsufficientStock):
            await ha.consume_by_name(db, "milk", Decimal("5"), "dl")


class TestShoppingAddItem:
    def test_defaults_to_one_piece(self) -> None:
        item_in = ha.shopping_add_item("dish soap", Decimal("1"), "pcs")
        assert item_in.name == "dish soap"
        assert item_in.quantity == Decimal("1")
        assert item_in.unit == "pcs"
        assert item_in.priority == "normal"
        assert item_in.source == "manual"
        assert item_in.product_master_id is None

    def test_an_amount_and_unit(self) -> None:
        # ShoppingListItemCreate canonicalizes on write (MVP-U1): "l" -> "dl", x10.
        item_in = ha.shopping_add_item("Milk", Decimal("2"), "l")
        assert (item_in.quantity, item_in.unit) == (Decimal("20"), "dl")
