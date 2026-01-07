"""Integration tests for WebSocket broadcasts from API endpoints."""
import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.db.seed_categories import seed_categories


class TestReceiptStatusBroadcasts:
    """Test receipt processing broadcasts status updates."""

    @pytest.mark.asyncio
    async def test_receipt_confirm_broadcasts_status(
        self,
        mocker,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test receipt confirmation broadcasts 'confirmed' status."""
        # Mock Redis publish to avoid actual Redis calls
        mock_redis = mocker.patch("app.services.broadcast_helpers.get_redis_client")
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        # Seed categories
        await seed_categories(db_session)
        await db_session.commit()

        # Create product
        product_data = {
            "canonical_name": "Test Milk 1L",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }
        product_response = await client.post("/api/products", json=product_data)
        assert product_response.status_code == 201
        product = product_response.json()

        # Create receipt (simplified - would normally upload file)
        # For this test, we'll create a receipt directly in the database
        from app.models.receipt import Receipt
        from uuid import uuid4

        receipt = Receipt(
            id=uuid4(),
            image_path="/fake/path/receipt.jpg",
            purchase_date=date.today(),
            processing_status="completed",
            items_extracted=1,
            items_matched=1,
            ocr_structured={
                "products": [
                    {
                        "name": "Milk",
                        "quantity": 1.0,
                        "unit": "pcs"
                    }
                ]
            }
        )
        db_session.add(receipt)
        await db_session.commit()

        # Confirm receipt
        confirm_data = {
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": 1.0,
                    "unit": "pcs",
                    "purchase_date": str(date.today())
                }
            ]
        }

        response = await client.post(
            f"/api/receipts/{receipt.id}/confirm",
            json=confirm_data
        )
        assert response.status_code == 200

        # Verify Redis publish was called (broadcast happened)
        assert mock_redis_instance.publish.called


class TestInventoryUpdateBroadcasts:
    """Test inventory endpoints broadcast updates."""

    @pytest.mark.asyncio
    async def test_create_inventory_broadcasts(
        self,
        mocker,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test creating inventory item broadcasts 'created' action."""
        # Mock Redis publish to avoid actual Redis calls
        mock_redis = mocker.patch("app.services.broadcast_helpers.get_redis_client")
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        # Seed categories
        await seed_categories(db_session)
        await db_session.commit()

        # Create product first
        product_data = {
            "canonical_name": "Test Milk 1L",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }
        product_response = await client.post("/api/products", json=product_data)
        assert product_response.status_code == 201
        product = product_response.json()

        # Create inventory item
        today = date.today()
        item_data = {
            "product_master_id": product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
        }

        response = await client.post("/api/inventory", json=item_data)
        assert response.status_code == 201

        # Verify Redis publish was called (broadcast happened)
        assert mock_redis_instance.publish.called

    @pytest.mark.asyncio
    async def test_update_inventory_broadcasts(
        self,
        mocker,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test updating inventory item broadcasts 'updated' action."""
        # Mock Redis publish to avoid actual Redis calls
        mock_redis = mocker.patch("app.services.broadcast_helpers.get_redis_client")
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        # Seed categories
        await seed_categories(db_session)
        await db_session.commit()

        # Create product
        product_data = {
            "canonical_name": "Test Cheese",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 25,
            "unit_type": "weight",
            "default_unit": "g",
        }
        product_response = await client.post("/api/products", json=product_data)
        product = product_response.json()

        # Create inventory item
        today = date.today()
        item_data = {
            "product_master_id": product["id"],
            "initial_quantity": 500,
            "current_quantity": 500,
            "unit": "g",
            "expiry_date": str(today + timedelta(days=25)),
        }
        create_response = await client.post("/api/inventory", json=item_data)
        item = create_response.json()

        # Reset mock to clear the create call
        mock_redis_instance.reset_mock()

        # Update inventory item
        update_data = {
            "status": "opened"
        }
        response = await client.patch(f"/api/inventory/{item['id']}", json=update_data)
        assert response.status_code == 200

        # Verify Redis publish was called (broadcast happened)
        assert mock_redis_instance.publish.called

    @pytest.mark.asyncio
    async def test_consume_inventory_broadcasts(
        self,
        mocker,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test consuming inventory item broadcasts 'consumed' action."""
        # Mock Redis publish to avoid actual Redis calls
        mock_redis = mocker.patch("app.services.broadcast_helpers.get_redis_client")
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        # Seed categories
        await seed_categories(db_session)
        await db_session.commit()

        # Create product
        product_data = {
            "canonical_name": "Test Orange Juice",
            "category": "beverages",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }
        product_response = await client.post("/api/products", json=product_data)
        product = product_response.json()

        # Create inventory item
        today = date.today()
        item_data = {
            "product_master_id": product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
        }
        create_response = await client.post("/api/inventory", json=item_data)
        item = create_response.json()

        # Reset mock to clear the create call
        mock_redis_instance.reset_mock()

        # Consume inventory item
        consume_data = {
            "quantity": 250
        }
        response = await client.post(
            f"/api/inventory/{item['id']}/consume",
            json=consume_data
        )
        assert response.status_code == 200

        # Verify Redis publish was called (broadcast happened)
        assert mock_redis_instance.publish.called

    @pytest.mark.asyncio
    async def test_delete_inventory_broadcasts(
        self,
        mocker,
        client: AsyncClient,
        db_session: AsyncSession
    ):
        """Test deleting inventory item broadcasts 'deleted' action."""
        # Mock Redis publish to avoid actual Redis calls
        mock_redis = mocker.patch("app.services.broadcast_helpers.get_redis_client")
        mock_redis_instance = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        # Seed categories
        await seed_categories(db_session)
        await db_session.commit()

        # Create product
        product_data = {
            "canonical_name": "Test Yogurt",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 14,
            "unit_type": "weight",
            "default_unit": "g",
        }
        product_response = await client.post("/api/products", json=product_data)
        product = product_response.json()

        # Create inventory item
        today = date.today()
        item_data = {
            "product_master_id": product["id"],
            "initial_quantity": 200,
            "current_quantity": 200,
            "unit": "g",
            "expiry_date": str(today + timedelta(days=14)),
        }
        create_response = await client.post("/api/inventory", json=item_data)
        item = create_response.json()

        # Reset mock to clear the create call
        mock_redis_instance.reset_mock()

        # Delete inventory item
        response = await client.delete(f"/api/inventory/{item['id']}")
        assert response.status_code == 204

        # Verify Redis publish was called (broadcast happened)
        assert mock_redis_instance.publish.called
