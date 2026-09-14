"""Generic product rules shared by receipt confirm and quick add (MVP-R2, MVP-S3)."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.product_master import ProductMaster
from app.services.generic_products import (
    InvalidProductRequest,
    ProductResolver,
    build_inventory_item,
)

PURCHASED = date(2026, 9, 14)


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    await seed_categories(db_session)
    await db_session.commit()


@pytest.fixture
async def milk(db_session: AsyncSession, categories) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Milk",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="volume",
        default_unit="dl",
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def _products(db: AsyncSession) -> int:
    return (
        await db.execute(select(func.count()).select_from(ProductMaster))
    ).scalar_one()


class TestResolve:
    async def test_by_id(self, db_session, milk):
        product, created = await ProductResolver(db_session).resolve(
            product_id=milk.id, unit="dl", quantity=Decimal(10)
        )
        assert (product.id, created) == (milk.id, False)

    async def test_name_is_reused_ignoring_case_and_spaces(self, db_session, milk):
        product, created = await ProductResolver(db_session).resolve(
            name="  mILK ", category="dairy", unit="dl", quantity=Decimal(10)
        )
        assert (product.id, created) == (milk.id, False)

    async def test_new_name_creates_a_product_from_the_category(
        self, db_session, categories
    ):
        product, created = await ProductResolver(db_session).resolve(
            name="Ground  beef", category="meat", unit="g", quantity=Decimal(400)
        )

        assert created is True
        assert product.canonical_name == "Ground beef"
        assert product.category == "meat"
        assert product.storage_type == "refrigerator"
        assert product.default_shelf_life_days == 5  # seeded meat shelf life
        assert (product.unit_type, product.default_unit) == ("weight", "g")
        assert float(product.default_quantity) == 400

    async def test_new_hand_typed_name_starts_with_a_capital(
        self, db_session, categories
    ):
        product, _ = await ProductResolver(db_session).resolve(
            name="oat drink", category="beverages", unit="dl", quantity=Decimal(10)
        )
        assert product.canonical_name == "Oat drink"

    async def test_same_new_name_twice_in_one_resolver_creates_one_product(
        self, db_session, categories
    ):
        resolver = ProductResolver(db_session)
        first, _ = await resolver.resolve(
            name="Peas", category="frozen", unit="g", quantity=Decimal(500)
        )
        second, created = await resolver.resolve(
            name="peas", category="frozen", unit="g", quantity=Decimal(500)
        )

        assert second.id == first.id
        assert created is False
        assert await _products(db_session) == 1

    @pytest.mark.parametrize(
        ("fields", "message"),
        [
            ({"product_id": uuid4()}, "not found"),
            ({"name": "Tofu"}, "Category required for new product 'Tofu'"),
            ({"name": "Tofu", "category": "vegan"}, "Unknown category 'vegan'"),
            ({"name": "   "}, "no product name"),
            ({}, "no product name"),
        ],
    )
    async def test_invalid_requests(self, db_session, categories, fields, message):
        with pytest.raises(InvalidProductRequest, match=message):
            await ProductResolver(db_session).resolve(
                unit="pcs", quantity=Decimal(1), **fields
            )
        assert await _products(db_session) == 0


class TestBuildInventoryItem:
    async def test_defaults_come_from_the_product(self, db_session, milk):
        item = build_inventory_item(
            milk, quantity=Decimal(10), unit="dl", purchase_date=PURCHASED
        )

        assert item.product_master_id == milk.id
        assert item.expiry_date == PURCHASED + timedelta(days=10)
        assert item.expiry_source == "calculated"
        assert item.location == "main_fridge"
        assert item.status == "sealed"
        assert (float(item.initial_quantity), float(item.current_quantity)) == (10, 10)
        assert item.receipt_id is None

    async def test_overrides(self, db_session, milk):
        receipt_id = uuid4()
        item = build_inventory_item(
            milk,
            quantity=Decimal(5),
            unit="dl",
            purchase_date=PURCHASED,
            expiry_date=date(2026, 12, 1),
            location="freezer",
            receipt_id=receipt_id,
        )

        assert (item.expiry_date, item.expiry_source) == (date(2026, 12, 1), "manual")
        assert item.location == "freezer"
        assert item.receipt_id == receipt_id
