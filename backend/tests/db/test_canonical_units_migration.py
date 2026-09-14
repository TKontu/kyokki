"""MVP-U1 data migration: stored quantities move to dl | tsp | tbsp | g | pcs."""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "a4f8c2d91e37_canonical_units.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "canonical_units_migration", MIGRATION
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def legacy_rows(db_session: AsyncSession) -> dict:
    db_session.add(
        Category(
            id="dairy",
            display_name="Dairy & Eggs",
            icon=None,
            default_shelf_life_days=7,
            meal_contexts=[],
            sort_order=1,
        )
    )
    await db_session.flush()

    def product(name: str, unit: str, unit_type: str, qty: str | None) -> ProductMaster:
        return ProductMaster(
            id=uuid4(),
            canonical_name=name,
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type=unit_type,
            default_unit=unit,
            default_quantity=Decimal(qty) if qty else None,
            min_stock_quantity=Decimal("500") if unit == "ml" else None,
        )

    products = {
        "milk": product("Milk 1L", "ml", "volume", "1000"),
        "cheese": product("Cheese", "kg", "weight", "0.4"),
        "eggs": product("Eggs", "unit", "unit", "10"),
        "spice": product("Cinnamon", "tsp", "volume", "20"),
        "imported": product("Syrup", "oz", "unit", "12"),
    }
    db_session.add_all(products.values())
    await db_session.flush()

    def item(product_key: str, unit: str, initial: str, current: str) -> InventoryItem:
        return InventoryItem(
            id=uuid4(),
            product_master_id=products[product_key].id,
            initial_quantity=Decimal(initial),
            current_quantity=Decimal(current),
            unit=unit,
            status="opened",
            expiry_date=date(2026, 10, 1),
        )

    items = {
        "milk": item("milk", "ml", "1000", "750"),
        "juice": item("milk", "L", "1.5", "1.5"),
        "cream": item("milk", "cl", "20", "20"),
        "cheese": item("cheese", "kg", "0.4", "0.4"),
        "eggs": item("eggs", "unit", "10", "8"),
        "kpl": item("eggs", "KPL", "6", "6"),
        "already": item("milk", "dl", "5", "5"),
        "spice": item("spice", "tsp", "20", "18"),
        "imported": item("imported", "oz", "12", "12"),
    }
    db_session.add_all(items.values())
    await db_session.flush()

    logs = {
        "milk": ConsumptionLog(
            inventory_item_id=items["milk"].id,
            product_master_id=products["milk"].id,
            action="use_partial",
            quantity_consumed=Decimal("250"),
        ),
        "eggs": ConsumptionLog(
            inventory_item_id=items["eggs"].id,
            product_master_id=products["eggs"].id,
            action="use_partial",
            quantity_consumed=Decimal("2"),
        ),
    }
    shopping = {
        "milk": ShoppingListItem(name="Milk", quantity=Decimal("2000"), unit="ml"),
        "flour": ShoppingListItem(name="Flour", quantity=Decimal("2"), unit="kg"),
    }
    db_session.add_all([*logs.values(), *shopping.values()])
    await db_session.commit()
    return {"products": products, "items": items, "logs": logs, "shopping": shopping}


async def _reload(db_session: AsyncSession, rows: dict) -> None:
    for group in rows.values():
        for obj in group.values():
            await db_session.refresh(obj)


async def test_convert_units(db_session: AsyncSession, legacy_rows: dict) -> None:
    migration = _load_migration()
    conn = await db_session.connection()

    unknown = await conn.run_sync(migration.convert_units)
    await db_session.commit()
    await _reload(db_session, legacy_rows)

    items = legacy_rows["items"]
    assert (
        items["milk"].unit,
        items["milk"].initial_quantity,
        items["milk"].current_quantity,
    ) == (
        "dl",
        Decimal("10.00"),
        Decimal("7.50"),
    )
    assert (items["juice"].unit, items["juice"].initial_quantity) == (
        "dl",
        Decimal("15.00"),
    )
    assert (items["cream"].unit, items["cream"].initial_quantity) == (
        "dl",
        Decimal("2.00"),
    )
    assert (items["cheese"].unit, items["cheese"].initial_quantity) == (
        "g",
        Decimal("400.00"),
    )
    assert (items["eggs"].unit, items["eggs"].current_quantity) == (
        "pcs",
        Decimal("8.00"),
    )
    assert (items["kpl"].unit, items["kpl"].initial_quantity) == (
        "pcs",
        Decimal("6.00"),
    )
    assert (items["already"].unit, items["already"].initial_quantity) == (
        "dl",
        Decimal("5.00"),
    )
    assert (items["spice"].unit, items["spice"].current_quantity) == (
        "tsp",
        Decimal("18.00"),
    )
    assert (items["imported"].unit, items["imported"].initial_quantity) == (
        "oz",
        Decimal("12.00"),
    )

    logs = legacy_rows["logs"]
    assert logs["milk"].quantity_consumed == Decimal("2.50")
    assert logs["eggs"].quantity_consumed == Decimal("2.00")

    products = legacy_rows["products"]
    milk = products["milk"]
    assert (
        milk.default_unit,
        milk.unit_type,
        milk.default_quantity,
        milk.min_stock_quantity,
    ) == (
        "dl",
        "volume",
        Decimal("10.00"),
        Decimal("5.00"),
    )
    assert (products["cheese"].default_unit, products["cheese"].unit_type) == (
        "g",
        "weight",
    )
    assert products["cheese"].default_quantity == Decimal("400.00")
    assert (products["eggs"].default_unit, products["eggs"].unit_type) == (
        "pcs",
        "count",
    )
    assert (products["spice"].default_unit, products["spice"].unit_type) == (
        "tsp",
        "volume",
    )
    assert products["imported"].default_unit == "oz"

    shopping = legacy_rows["shopping"]
    assert (shopping["milk"].quantity, shopping["milk"].unit) == (
        Decimal("20.00"),
        "dl",
    )
    assert (shopping["flour"].quantity, shopping["flour"].unit) == (
        Decimal("2000.00"),
        "g",
    )

    assert unknown == {
        "inventory_item": 1,
        "product_master": 1,
        "shopping_list_item": 0,
    }


async def test_convert_units_is_idempotent(
    db_session: AsyncSession, legacy_rows: dict
) -> None:
    migration = _load_migration()
    conn = await db_session.connection()

    await conn.run_sync(migration.convert_units)
    await conn.run_sync(migration.convert_units)
    await db_session.commit()
    await _reload(db_session, legacy_rows)

    assert legacy_rows["items"]["milk"].initial_quantity == Decimal("10.00")
    assert legacy_rows["logs"]["milk"].quantity_consumed == Decimal("2.50")
    assert legacy_rows["products"]["cheese"].default_quantity == Decimal("400.00")


async def test_revert_units_restores_millilitres(
    db_session: AsyncSession, legacy_rows: dict
) -> None:
    migration = _load_migration()
    conn = await db_session.connection()

    await conn.run_sync(migration.convert_units)
    await conn.run_sync(migration.revert_units)
    await db_session.commit()
    await _reload(db_session, legacy_rows)

    items = legacy_rows["items"]
    assert (items["milk"].unit, items["milk"].initial_quantity) == (
        "ml",
        Decimal("1000.00"),
    )
    assert legacy_rows["logs"]["milk"].quantity_consumed == Decimal("250.00")
    assert legacy_rows["products"]["milk"].default_unit == "ml"
    assert legacy_rows["shopping"]["milk"].unit == "ml"
    # Lossy by design: kg and unit rows stay in their canonical form
    assert (items["cheese"].unit, items["cheese"].initial_quantity) == (
        "g",
        Decimal("400.00"),
    )
    assert items["eggs"].unit == "pcs"


def test_migration_follows_the_previous_head() -> None:
    migration = _load_migration()
    assert migration.down_revision == "7c1f2a9d4b30"
    assert set(migration.UNIT_MAP) >= {
        "ml",
        "cl",
        "l",
        "dl",
        "kg",
        "g",
        "unit",
        "kpl",
        "tsp",
        "tbsp",
    }
