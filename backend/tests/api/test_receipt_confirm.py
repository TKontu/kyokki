"""Tests for receipt confirmation endpoint."""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.category import Category
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.services.generic_products import build_inventory_item


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
        sort_order=1,
    )
    test_db.add(category)
    await test_db.commit()
    await test_db.refresh(category)
    return category


@pytest.fixture
async def sample_product(
    test_db: AsyncSession, sample_category: Category
) -> ProductMaster:
    """Create sample product."""
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Valio Whole Milk 1L",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
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
        from datetime import date

        from sqlalchemy import select

        from app.models.inventory_item import InventoryItem

        stmt = select(InventoryItem).where(InventoryItem.receipt_id == receipt_id)
        db_result = await test_db.execute(stmt)
        inventory_item = db_result.scalar_one()

        assert inventory_item.expiry_date is not None
        # Should be purchase_date + default_shelf_life_days (7 days)
        assert inventory_item.expiry_date == date(2024, 1, 13)
        assert inventory_item.expiry_source == "calculated"


class TestConfirmCanonicalUnits:
    """MVP-U1: confirmed receipt quantities are stored in canonical units."""

    async def test_confirmed_kilograms_become_grams(
        self, client: AsyncClient, test_db: AsyncSession, processed_receipt: dict
    ):
        response = await client.post(
            f"/api/receipts/{processed_receipt['id']}/confirm",
            json={
                "items": [
                    {
                        "product_id": processed_receipt["product_id"],
                        "quantity": 0.386,
                        "unit": "kg",
                        "purchase_date": "2024-01-06",
                    }
                ]
            },
        )
        assert response.status_code == 200

        from sqlalchemy import select

        from app.models.inventory_item import InventoryItem

        item = (
            await test_db.execute(
                select(InventoryItem).where(
                    InventoryItem.receipt_id == processed_receipt["id"]
                )
            )
        ).scalar_one()
        assert (item.unit, float(item.initial_quantity)) == ("g", 386.0)

    async def test_unknown_unit_is_rejected(
        self, client: AsyncClient, test_db: AsyncSession, processed_receipt: dict
    ):
        response = await client.post(
            f"/api/receipts/{processed_receipt['id']}/confirm",
            json={
                "items": [
                    {
                        "product_id": processed_receipt["product_id"],
                        "quantity": 1,
                        "unit": "oz",
                        "purchase_date": "2024-01-06",
                    }
                ]
            },
        )
        assert response.status_code == 422


class TestConfirmNewProducts:
    """MVP-R2: confirm creates generic products, rejects repeats and unread receipts."""

    async def test_new_item_creates_a_product(
        self, client: AsyncClient, test_db: AsyncSession, processed_receipt: dict
    ):
        response = await client.post(
            f"/api/receipts/{processed_receipt['id']}/confirm",
            json={
                "items": [
                    {
                        "name": "Ground beef",
                        "category": "dairy",
                        "quantity": 400,
                        "unit": "g",
                        "purchase_date": "2024-01-06",
                        "location": "freezer",
                    }
                ]
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert (body["items_created"], body["products_created"]) == (1, 1)
        assert body["aliases_learned"] == 0

    async def test_second_confirm_is_a_conflict(
        self, client: AsyncClient, test_db: AsyncSession, processed_receipt: dict
    ):
        url = f"/api/receipts/{processed_receipt['id']}/confirm"
        item = {
            "product_id": processed_receipt["product_id"],
            "quantity": 1,
            "unit": "pcs",
            "purchase_date": "2024-01-06",
        }

        first = await client.post(url, json={"items": [item]})
        second = await client.post(url, json={"items": [item]})

        assert first.status_code == 200
        assert second.status_code == 409
        assert "already confirmed" in second.json()["detail"]

    async def test_unread_receipt_is_a_conflict(
        self, client: AsyncClient, test_db: AsyncSession, sample_category: Category
    ):
        files = {"file": ("r.jpg", BytesIO(b"unread receipt"), "image/jpeg")}
        receipt_id = (await client.post("/api/receipts/scan", files=files)).json()["id"]

        response = await client.post(
            f"/api/receipts/{receipt_id}/confirm", json={"items": []}
        )

        assert response.status_code == 409
        assert "not ready" in response.json()["detail"]

    async def test_new_item_without_category_is_rejected(
        self, client: AsyncClient, test_db: AsyncSession, processed_receipt: dict
    ):
        response = await client.post(
            f"/api/receipts/{processed_receipt['id']}/confirm",
            json={
                "items": [
                    {
                        "name": "Plastic bag",
                        "quantity": 1,
                        "unit": "pcs",
                        "purchase_date": "2024-01-06",
                    }
                ]
            },
        )

        assert response.status_code == 400
        assert "Category required" in response.json()["detail"]

    async def test_item_without_product_name_or_line_is_invalid(
        self, client: AsyncClient, test_db: AsyncSession, processed_receipt: dict
    ):
        response = await client.post(
            f"/api/receipts/{processed_receipt['id']}/confirm",
            json={
                "items": [{"quantity": 1, "unit": "pcs", "purchase_date": "2024-01-06"}]
            },
        )

        assert response.status_code == 422


class TestConfirmMovesStock:
    """Q19: a confirm whose receipt replaces a product's placeholder shelf life re-dates the
    stock that placeholder dated, and says so over the WebSocket once it has committed."""

    async def test_the_re_dated_item_is_broadcast(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        processed_receipt: dict,
        sample_product: ProductMaster,
    ):
        bought = date(2026, 9, 1)
        sample_product.shelf_life_source = "category"
        in_the_fridge = build_inventory_item(
            sample_product, quantity=Decimal("5"), purchase_date=bought
        )
        test_db.add(in_the_fridge)
        receipt = await test_db.get(Receipt, UUID(processed_receipt["id"]))
        assert receipt is not None
        # The model read the milk off this receipt and estimated how long it keeps
        receipt.ocr_structured = {
            "lines": [{"name": "Valio Whole Milk 1L", "shelf_life_days": 12}]
        }
        await test_db.commit()
        in_the_fridge_id = in_the_fridge.id
        assert in_the_fridge.expiry_date == bought + timedelta(days=7)

        with patch(
            "app.services.receipt_confirm.broadcast_inventory_update",
            new_callable=AsyncMock,
        ) as broadcast:
            response = await client.post(
                f"/api/receipts/{processed_receipt['id']}/confirm",
                json={
                    "items": [
                        {
                            "index": 0,
                            "product_id": processed_receipt["product_id"],
                            "quantity": 1,
                            "unit": "dl",
                            "purchase_date": "2026-09-20",
                        }
                    ]
                },
            )

        assert response.status_code == 200, response.text
        moved = await test_db.get(
            InventoryItem, in_the_fridge_id, populate_existing=True
        )
        assert moved is not None
        assert moved.expiry_date == bought + timedelta(days=12)
        updates = [
            call.kwargs
            for call in broadcast.await_args_list
            if call.kwargs["action"] == "updated"
        ]
        assert updates == [
            {
                "inventory_item_id": in_the_fridge_id,
                "action": "updated",
                "current_quantity": Decimal("5"),
                "status": "sealed",
            }
        ]
        created = [
            call.kwargs
            for call in broadcast.await_args_list
            if call.kwargs["action"] == "created"
        ]
        assert len(created) == 1
