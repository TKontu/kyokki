"""Tests for receipt confirmation endpoint."""
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt


@pytest.fixture
async def test_db(db_session: AsyncSession):
    """Provide test database session with dependency override."""
    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield db_session
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_category(test_db: AsyncSession) -> Category:
    """Create sample category."""
    category = Category(
        id="dairy",
        display_name="Dairy",
        icon="🥛",
        default_shelf_life_days=7,
        meal_contexts=["breakfast"],
        sort_order=1,
    )
    test_db.add(category)
    await test_db.commit()
    await test_db.refresh(category)
    return category


@pytest.fixture
async def sample_product(test_db: AsyncSession, sample_category: Category) -> ProductMaster:
    """Create sample product."""
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Valio Whole Milk 1L",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="ml",
        default_quantity=Decimal("1000"),
    )
    test_db.add(product)
    await test_db.commit()
    await test_db.refresh(product)
    return product


@pytest.fixture
async def processed_receipt(
    client: AsyncClient,
    test_db: AsyncSession,
    sample_product: ProductMaster,
) -> dict:
    """Create and process a receipt."""
    # Upload receipt
    file_content = b"fake receipt"
    files = {"file": ("receipt.jpg", BytesIO(file_content), "image/jpeg")}
    create_response = await client.post("/api/receipts/scan", files=files)
    receipt_id = create_response.json()["id"]

    # Manually update receipt to simulate processing
    from sqlalchemy import select
    from app.models.receipt import Receipt

    stmt = select(Receipt).where(Receipt.id == receipt_id)
    result = await test_db.execute(stmt)
    receipt = result.scalar_one()

    receipt.processing_status = "completed"
    receipt.ocr_structured = {
        "products": [
            {
                "name": "Valio Whole Milk 1L",
                "quantity": 2.0,
                "unit": "pcs",
                "price": 2.49,
            }
        ]
    }
    receipt.items_extracted = 1
    receipt.items_matched = 1

    await test_db.commit()

    return {"id": str(receipt_id), "product_id": str(sample_product.id)}


class TestConfirmReceipt:
    """Test POST /api/receipts/{id}/confirm endpoint."""

    async def test_confirm_receipt_creates_inventory(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        processed_receipt: dict,
    ):
        """POST /api/receipts/{id}/confirm should create inventory items."""
        receipt_id = processed_receipt["id"]
        product_id = processed_receipt["product_id"]

        confirm_data = {
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 2.0,
                    "unit": "pcs",
                    "purchase_date": "2024-01-06",
                }
            ]
        }

        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm",
            json=confirm_data,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["items_created"] == 1

        # Verify inventory was created
        from sqlalchemy import select
        from app.models.inventory_item import InventoryItem

        stmt = select(InventoryItem).where(InventoryItem.receipt_id == receipt_id)
        db_result = await test_db.execute(stmt)
        inventory_items = db_result.scalars().all()

        assert len(inventory_items) == 1
        assert str(inventory_items[0].product_master_id) == product_id
        assert float(inventory_items[0].initial_quantity) == 2.0

    async def test_confirm_receipt_not_found(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
    ):
        """POST /api/receipts/{id}/confirm should return 404 for non-existent receipt."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        confirm_data = {"items": []}

        response = await client.post(
            f"/api/receipts/{fake_uuid}/confirm",
            json=confirm_data,
        )

        assert response.status_code == 404

    async def test_confirm_receipt_invalid_product(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        processed_receipt: dict,
    ):
        """POST /api/receipts/{id}/confirm should return 400 for invalid product ID."""
        receipt_id = processed_receipt["id"]
        fake_product_id = "00000000-0000-0000-0000-000000000000"

        confirm_data = {
            "items": [
                {
                    "product_id": fake_product_id,
                    "quantity": 1.0,
                    "unit": "pcs",
                    "purchase_date": "2024-01-06",
                }
            ]
        }

        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm",
            json=confirm_data,
        )

        assert response.status_code == 400
        assert "product" in response.json()["detail"].lower()

    async def test_confirm_receipt_empty_items(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        processed_receipt: dict,
    ):
        """POST /api/receipts/{id}/confirm should handle empty items list."""
        receipt_id = processed_receipt["id"]
        confirm_data = {"items": []}

        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm",
            json=confirm_data,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["items_created"] == 0

    async def test_confirm_receipt_multiple_items(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        processed_receipt: dict,
        sample_category: Category,
    ):
        """POST /api/receipts/{id}/confirm should handle multiple items."""
        receipt_id = processed_receipt["id"]
        product_id = processed_receipt["product_id"]

        # Create second product
        product2 = ProductMaster(
            id=uuid4(),
            canonical_name="Arla Butter 500g",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=60,
            unit_type="weight",
            default_unit="g",
            default_quantity=Decimal("500"),
        )
        test_db.add(product2)
        await test_db.commit()

        confirm_data = {
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 2.0,
                    "unit": "pcs",
                    "purchase_date": "2024-01-06",
                },
                {
                    "product_id": str(product2.id),
                    "quantity": 1.0,
                    "unit": "pcs",
                    "purchase_date": "2024-01-06",
                },
            ]
        }

        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm",
            json=confirm_data,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["items_created"] == 2

    async def test_confirm_receipt_calculates_expiry(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        processed_receipt: dict,
    ):
        """POST /api/receipts/{id}/confirm should calculate expiry dates."""
        receipt_id = processed_receipt["id"]
        product_id = processed_receipt["product_id"]

        confirm_data = {
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 1.0,
                    "unit": "pcs",
                    "purchase_date": "2024-01-06",
                }
            ]
        }

        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm",
            json=confirm_data,
        )

        assert response.status_code == 200

        # Verify expiry date was calculated
        from sqlalchemy import select
        from app.models.inventory_item import InventoryItem
        from datetime import date

        stmt = select(InventoryItem).where(InventoryItem.receipt_id == receipt_id)
        db_result = await test_db.execute(stmt)
        inventory_item = db_result.scalar_one()

        assert inventory_item.expiry_date is not None
        # Should be purchase_date + default_shelf_life_days (7 days)
        assert inventory_item.expiry_date == date(2024, 1, 13)
        assert inventory_item.expiry_source == "calculated"
