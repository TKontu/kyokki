"""Tests for ProductMaster model."""
import pytest
from sqlalchemy import select
from decimal import Decimal

from app.models.category import Category
from app.models.product_master import ProductMaster


@pytest.mark.asyncio
class TestProductMasterModel:
    """Test suite for ProductMaster model CRUD operations."""

    @pytest.fixture
    async def dairy_category(self, db_session):
        """Create dairy category for testing."""
        category = Category(
            id="dairy",
            display_name="Dairy Products",
            default_shelf_life_days=7,
            sort_order=1,
        )
        db_session.add(category)
        await db_session.commit()
        return category

    async def test_create_product(self, db_session, dairy_category):
        """Test creating a new product."""
        product = ProductMaster(
            canonical_name="Valio Whole Milk 1L",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            opened_shelf_life_days=4,
            unit_type="volume",
            default_unit="ml",
            default_quantity=Decimal("1000"),
            min_stock_quantity=Decimal("2000"),
            reorder_quantity=Decimal("2000"),
        )

        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        assert product.id is not None
        assert product.canonical_name == "Valio Whole Milk 1L"
        assert product.category == "dairy"
        assert product.default_quantity == Decimal("1000")
        assert product.created_at is not None
        assert product.updated_at is not None

    async def test_product_with_off_data(self, db_session, dairy_category):
        """Test creating product with Open Food Facts data."""
        off_data = {
            "product_name": "Valio Milk",
            "brands": "Valio",
            "nutriscore_grade": "b",
            "image_url": "https://example.com/image.jpg",
        }

        product = ProductMaster(
            canonical_name="Valio Milk",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="ml",
            off_product_id="1234567890123",
            off_data=off_data,
        )

        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        assert product.off_product_id == "1234567890123"
        assert product.off_data["product_name"] == "Valio Milk"
        assert product.off_data["nutriscore_grade"] == "b"

    async def test_update_product(self, db_session, dairy_category):
        """Test updating a product."""
        product = ProductMaster(
            canonical_name="Test Product",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="ml",
        )
        db_session.add(product)
        await db_session.commit()

        # Update product
        product.canonical_name = "Updated Product"
        product.default_shelf_life_days = 10
        product.min_stock_quantity = Decimal("1000")
        await db_session.commit()
        await db_session.refresh(product)

        assert product.canonical_name == "Updated Product"
        assert product.default_shelf_life_days == 10
        assert product.min_stock_quantity == Decimal("1000")

    async def test_read_product_by_id(self, db_session, dairy_category):
        """Test reading a product by ID."""
        product = ProductMaster(
            canonical_name="Test Milk",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="ml",
        )
        db_session.add(product)
        await db_session.commit()
        product_id = product.id

        # Read product
        result = await db_session.execute(
            select(ProductMaster).filter(ProductMaster.id == product_id)
        )
        fetched_product = result.scalars().first()

        assert fetched_product is not None
        assert fetched_product.id == product_id
        assert fetched_product.canonical_name == "Test Milk"

    async def test_search_products_by_category(self, db_session, dairy_category):
        """Test searching products by category."""
        products = [
            ProductMaster(
                canonical_name="Milk",
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=7,
                unit_type="volume",
                default_unit="ml",
            ),
            ProductMaster(
                canonical_name="Cheese",
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=25,
                unit_type="weight",
                default_unit="g",
            ),
        ]

        for product in products:
            db_session.add(product)
        await db_session.commit()

        # Search by category
        result = await db_session.execute(
            select(ProductMaster).filter(ProductMaster.category == "dairy")
        )
        dairy_products = result.scalars().all()

        assert len(dairy_products) == 2
        assert all(p.category == "dairy" for p in dairy_products)

    async def test_delete_product(self, db_session, dairy_category):
        """Test deleting a product."""
        product = ProductMaster(
            canonical_name="To Delete",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="ml",
        )
        db_session.add(product)
        await db_session.commit()
        product_id = product.id

        # Delete product
        await db_session.delete(product)
        await db_session.commit()

        # Verify deletion
        result = await db_session.execute(
            select(ProductMaster).filter(ProductMaster.id == product_id)
        )
        fetched_product = result.scalars().first()

        assert fetched_product is None
