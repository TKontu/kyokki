"""AG6: a shopping list from what is below its minimum stock (services/shopping_generate.py)."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem
from app.services import shopping_generate
from app.services.shopping_generate import InvalidGenerate

TODAY = date.today()
LOW = ["low_stock"]


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
    unit_type = {"dl": "volume", "l": "volume", "g": "weight", "pcs": "count"}[unit]
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
        location="main_fridge",
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
    purchased: bool = False,
) -> ShoppingListItem:
    item = ShoppingListItem(
        id=uuid4(),
        product_master_id=product.id,
        name=product.canonical_name,
        quantity=Decimal(quantity),
        unit=unit,
        priority="normal",
        source="manual",
        is_purchased=purchased,
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


class TestWhatIsLow:
    async def test_below_the_minimum_adds_the_shortfall(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.dry_run is False
        assert [line.product_id for line in result.added] == [milk.id]
        line = result.added[0]
        assert (line.name, line.need, line.unit) == ("Milk", Decimal("6"), "dl")
        assert (line.on_hand, line.min_stock) == (Decimal("4"), Decimal("10"))
        assert result.updated == result.unchanged == result.skipped == []
        [item] = await _items(db)
        assert line.item_id == item.id
        assert (item.product_master_id, item.name) == (milk.id, "Milk")
        assert (item.quantity, item.unit) == (Decimal("6"), "dl")
        assert (item.source, item.priority, item.is_purchased) == (
            "auto_restock",
            "normal",
            False,
        )

    async def test_at_the_minimum_needs_nothing(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "6")
        await _stock(db, milk, "4")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.added == result.updated == result.unchanged == []
        assert await _count(db) == 0

    async def test_above_the_minimum_needs_nothing(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "12")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.added == []
        assert await _count(db) == 0

    async def test_no_stock_counts_as_zero(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        # Used up and thrown away: neither is stock.
        await _stock(db, milk, "0", status="empty")
        await _stock(db, milk, "5", status="discarded")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        [line] = result.added
        assert (line.on_hand, line.need) == (Decimal("0"), Decimal("10"))

    async def test_reorder_quantity_is_the_need_when_set(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10", reorder="20")
        await _stock(db, milk, "4")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.added[0].need == Decimal("20")
        [item] = await _items(db)
        assert item.quantity == Decimal("20")

    async def test_a_product_without_a_minimum_is_ignored(self, db) -> None:
        await _product(db, "Milk")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.added == result.skipped == []

    async def test_stock_in_a_compatible_unit_is_converted(self, db) -> None:
        juice = await _product(db, "Juice", unit="l", min_stock="2")
        await _stock(db, juice, "5", unit="dl")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        [line] = result.added
        assert (line.on_hand, line.need, line.unit) == (
            Decimal("0.5"),
            Decimal("1.5"),
            "l",
        )
        [item] = await _items(db)
        assert (item.quantity, item.unit) == (Decimal("15"), "dl")

    async def test_stock_in_an_incompatible_unit_is_skipped(self, db) -> None:
        eggs = await _product(db, "Eggs", unit="pcs", min_stock="6")
        await _stock(db, eggs, "300", unit="g")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.added == []
        [line] = result.skipped
        assert line.product_id == eggs.id
        assert line.reason and "g" in line.reason and "pcs" in line.reason
        assert await _count(db) == 0


class TestMerging:
    async def test_an_open_item_is_raised_to_the_need(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")
        open_item = await _open_item(db, milk, "2")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        assert result.added == []
        [line] = result.updated
        assert (line.item_id, line.need) == (open_item.id, Decimal("6"))
        [item] = await _items(db)
        assert (item.id, item.quantity) == (open_item.id, Decimal("6"))
        # Whoever put it there still owns it.
        assert item.source == "manual"

    async def test_an_open_item_already_big_enough_is_unchanged(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")
        open_item = await _open_item(db, milk, "8")

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        [line] = result.unchanged
        assert line.item_id == open_item.id
        [item] = await _items(db)
        assert item.quantity == Decimal("8")

    async def test_generating_twice_adds_no_duplicate(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")

        first = await shopping_generate.generate(db, LOW, dry_run=False)
        second = await shopping_generate.generate(db, LOW, dry_run=False)

        assert len(first.added) == 1
        assert second.added == second.updated == []
        assert [line.item_id for line in second.unchanged] == [first.added[0].item_id]
        assert await _count(db) == 1

    async def test_a_purchased_item_is_not_reused(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")
        bought = await _open_item(db, milk, "6", purchased=True)

        result = await shopping_generate.generate(db, LOW, dry_run=False)

        [line] = result.added
        assert line.item_id != bought.id
        assert await _count(db) == 2


class TestDryRun:
    async def test_a_dry_run_plans_the_same_and_writes_nothing(self, db) -> None:
        milk = await _product(db, "Milk", min_stock="10")
        await _stock(db, milk, "4")
        butter = await _product(db, "Butter", unit="g", min_stock="500")
        open_item = await _open_item(db, butter, "100", unit="g")
        # A dry run rolls back, which expires every loaded object.
        milk_id, open_item_id = milk.id, open_item.id

        plan = await shopping_generate.generate(db, LOW, dry_run=True)

        assert plan.dry_run is True
        assert [(line.product_id, line.need) for line in plan.added] == [
            (milk_id, Decimal("6"))
        ]
        assert plan.added[0].item_id is None
        assert [(line.item_id, line.need) for line in plan.updated] == [
            (open_item_id, Decimal("500"))
        ]
        [item] = await _items(db)
        assert item.quantity == Decimal("100")

        real = await shopping_generate.generate(db, LOW, dry_run=False)
        assert [(line.product_id, line.need) for line in real.added] == [
            (milk_id, Decimal("6"))
        ]
        assert [(line.item_id, line.need) for line in real.updated] == [
            (open_item_id, Decimal("500"))
        ]


class TestSources:
    @pytest.mark.parametrize("sources", [[], ["recipe"], ["low_stock", "meal_plan"]])
    async def test_only_low_stock_is_a_source(self, db, sources) -> None:
        with pytest.raises(InvalidGenerate):
            await shopping_generate.generate(db, sources, dry_run=False)
