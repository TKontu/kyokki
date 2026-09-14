"""Quick add: one call adds stock for an existing or new generic product (MVP-S3)."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.inventory_item import QuickAddRequest
from app.services.generic_products import InvalidProductRequest
from app.services.quick_add import quick_add


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    await seed_categories(db_session)
    await db_session.commit()


async def _count(db: AsyncSession, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_new_product_and_item_in_one_call(db_session, categories):
    result = await quick_add(
        db_session,
        QuickAddRequest(name="Peas", category="frozen", quantity=500, unit="g"),
    )

    assert result.product_created is True
    item = result.item
    assert item.product_name == "Peas"
    assert item.category_name
    assert item.location == "freezer"
    assert item.expiry_source == "calculated"
    assert item.purchase_date == date.today()
    assert await _count(db_session, ProductMaster) == 1
    assert await _count(db_session, InventoryItem) == 1


async def test_existing_name_is_reused(db_session, categories):
    await quick_add(
        db_session,
        QuickAddRequest(name="Milk", category="dairy", quantity=10, unit="dl"),
    )

    result = await quick_add(
        db_session, QuickAddRequest(name="milk", quantity=5, unit="dl")
    )

    assert result.product_created is False
    assert await _count(db_session, ProductMaster) == 1
    assert await _count(db_session, InventoryItem) == 2


async def test_by_product_id_with_overrides(db_session, categories):
    first = await quick_add(
        db_session,
        QuickAddRequest(name="Milk", category="dairy", quantity=10, unit="dl"),
    )

    result = await quick_add(
        db_session,
        QuickAddRequest(
            product_id=first.item.product_master_id,
            quantity=1.5,
            unit="l",
            location="pantry",
            purchase_date=date(2026, 9, 1),
            expiry_date=date(2026, 9, 30),
        ),
    )

    item = result.item
    assert (item.unit, float(item.current_quantity)) == ("dl", 15)
    assert item.location == "pantry"
    assert (item.purchase_date, item.expiry_date, item.expiry_source) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
        "manual",
    )


async def test_calculated_expiry_uses_the_product_shelf_life(db_session, categories):
    result = await quick_add(
        db_session,
        QuickAddRequest(
            name="Ground beef",
            category="meat",
            quantity=400,
            unit="g",
            purchase_date=date(2026, 9, 14),
        ),
    )
    assert result.item.expiry_date == date(2026, 9, 14) + timedelta(days=5)


async def test_invalid_request_writes_nothing(db_session, categories):
    with pytest.raises(InvalidProductRequest, match="Category required"):
        await quick_add(
            db_session, QuickAddRequest(name="Tofu", quantity=1, unit="pcs")
        )

    assert await _count(db_session, ProductMaster) == 0
    assert await _count(db_session, InventoryItem) == 0


async def test_failure_after_writing_rolls_back(db_session, categories):
    with (
        patch(
            "app.services.quick_add.crud_inventory.get_inventory_item",
            side_effect=RuntimeError("db gone"),
        ),
        pytest.raises(RuntimeError),
    ):
        await quick_add(
            db_session,
            QuickAddRequest(
                name="Peas", category="frozen", quantity=Decimal(1), unit="pcs"
            ),
        )


class TestRequestSchema:
    def test_needs_a_product_or_a_name(self):
        with pytest.raises(ValidationError, match="product_id or name"):
            QuickAddRequest(quantity=1, unit="pcs")

    def test_blank_name_does_not_count(self):
        with pytest.raises(ValidationError, match="product_id or name"):
            QuickAddRequest(name="  ", quantity=1, unit="pcs")

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_quantity_must_be_positive(self, quantity):
        with pytest.raises(ValidationError):
            QuickAddRequest(name="Milk", quantity=quantity, unit="dl")

    def test_unknown_unit_is_rejected(self):
        with pytest.raises(ValidationError):
            QuickAddRequest(name="Milk", quantity=1, unit="oz")

    def test_location_is_validated(self):
        with pytest.raises(ValidationError):
            QuickAddRequest(name="Milk", quantity=1, unit="dl", location="garage")
