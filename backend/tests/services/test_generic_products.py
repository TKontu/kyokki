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
    quantity_for_product,
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


class TestProductLearnsItsOwnShape:
    """Q2/Q3/Q6: a product should know how it is counted and how long it keeps."""

    async def test_a_new_product_keeps_what_the_model_worked_out(
        self, db_session: AsyncSession, categories
    ):
        product, created = await ProductResolver(db_session).resolve(
            name="Apple",
            category="produce",
            unit="g",
            quantity=1072,
            piece_grams=125,
            shelf_life_days=21,
        )

        assert created is True
        assert product.avg_piece_grams == Decimal("125.00")
        assert product.default_shelf_life_days == 21
        # knowing a piece weight means the cook counts them, whatever the receipt printed
        assert (product.default_unit, product.unit_type) == ("pcs", "count")

    async def test_without_an_estimate_the_category_still_decides(
        self, db_session: AsyncSession, categories
    ):
        product, _ = await ProductResolver(db_session).resolve(
            name="Ground beef", category="produce", unit="g", quantity=400
        )

        assert product.avg_piece_grams is None
        assert (
            product.default_shelf_life_days == 5
        )  # the produce category's blanket figure
        assert product.default_unit == "g"

    async def test_a_later_receipt_fills_in_a_missing_piece_weight(
        self, db_session: AsyncSession, categories
    ):
        resolver = ProductResolver(db_session)
        first, _ = await resolver.resolve(
            name="Apple", category="produce", unit="pcs", quantity=1
        )
        assert first.avg_piece_grams is None

        again, created = await ProductResolver(db_session).resolve(
            name="Apple", category="produce", unit="g", quantity=1072, piece_grams=125
        )

        assert created is False
        assert again.avg_piece_grams == Decimal("125")

    async def test_a_later_receipt_never_overwrites_what_is_known(
        self, db_session: AsyncSession, categories
    ):
        """Otherwise every weekly shop would undo a correction."""
        first, _ = await ProductResolver(db_session).resolve(
            name="Apple", category="produce", unit="g", quantity=1072, piece_grams=125
        )

        again, _ = await ProductResolver(db_session).resolve(
            name="apple", category="produce", unit="g", quantity=500, piece_grams=300
        )

        assert again.avg_piece_grams == Decimal("125.00")


class TestQuantityForProduct:
    """Q2: what actually lands in stock."""

    def _product(self, **kwargs) -> ProductMaster:
        defaults = dict(
            canonical_name="Apple",
            category="produce",
            storage_type="refrigerator",
            default_shelf_life_days=21,
            unit_type="count",
            default_unit="pcs",
            avg_piece_grams=Decimal("125"),
        )
        return ProductMaster(**{**defaults, **kwargs})

    def test_a_weighed_purchase_is_stored_as_pieces(self):
        assert quantity_for_product(self._product(), 1072, "g") == (9, "pcs")

    def test_a_product_with_no_piece_weight_is_left_alone(self):
        product = self._product(avg_piece_grams=None)

        assert quantity_for_product(product, 1072, "g") == (1072, "g")

    def test_a_product_counted_by_weight_is_left_alone(self):
        product = self._product(default_unit="g", unit_type="weight")

        assert quantity_for_product(product, 400, "g") == (400, "g")

    def test_buying_them_by_the_piece_needs_no_conversion(self):
        assert quantity_for_product(self._product(), 3, "pcs") == (3, "pcs")

    async def test_confirm_puts_apples_in_the_fridge_as_apples(
        self, db_session: AsyncSession, categories
    ):
        product, _ = await ProductResolver(db_session).resolve(
            name="Apple",
            category="produce",
            unit="g",
            quantity=1072,
            piece_grams=125,
            shelf_life_days=21,
        )

        item = build_inventory_item(
            product, quantity=1072, unit="g", purchase_date=PURCHASED
        )

        assert (item.initial_quantity, item.unit) == (9, "pcs")
        assert item.current_quantity == 9
        # and Q6: the product's own shelf life, not the category's
        assert item.expiry_date == PURCHASED + timedelta(days=21)
        assert item.expiry_source == "calculated"


class TestOpenedShelfLifeOnProducts:
    """Q5: the product remembers how long it keeps once opened."""

    async def test_a_new_product_keeps_the_models_estimate(
        self, db_session: AsyncSession, categories
    ):
        product, created = await ProductResolver(db_session).resolve(
            name="Cream",
            category="dairy",
            unit="dl",
            quantity=2,
            shelf_life_days=14,
            opened_shelf_life_days=5,
        )

        assert created is True
        assert product.opened_shelf_life_days == 5

    async def test_a_later_receipt_fills_a_missing_one(
        self, db_session: AsyncSession, categories
    ):
        first, _ = await ProductResolver(db_session).resolve(
            name="Cream", category="dairy", unit="dl", quantity=2
        )
        assert first.opened_shelf_life_days is None

        again, created = await ProductResolver(db_session).resolve(
            name="cream",
            category="dairy",
            unit="dl",
            quantity=2,
            opened_shelf_life_days=5,
        )

        assert created is False
        assert again.opened_shelf_life_days == 5

    async def test_a_later_receipt_never_overwrites_a_known_one(
        self, db_session: AsyncSession, categories
    ):
        await ProductResolver(db_session).resolve(
            name="Cream",
            category="dairy",
            unit="dl",
            quantity=2,
            opened_shelf_life_days=5,
        )

        again, _ = await ProductResolver(db_session).resolve(
            name="Cream",
            category="dairy",
            unit="dl",
            quantity=2,
            opened_shelf_life_days=30,
        )

        assert again.opened_shelf_life_days == 5
