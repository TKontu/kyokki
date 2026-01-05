"""Tests for Inventory CRUD API endpoints."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.seed_categories import seed_categories
from app.db.session import get_db
from app.main import app


@pytest.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    """Provide a database session with seeded categories and override app dependency."""
    # Override the dependency to use test database session
    async def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Seed categories (required for foreign key)
    await seed_categories(db_session)
    await db_session.commit()

    yield db_session

    # Clean up override
    app.dependency_overrides.clear()


@pytest.fixture
async def test_product(client: AsyncClient, seeded_db: AsyncSession) -> dict:
    """Create a test product for inventory items."""
    product_data = {
        "canonical_name": "Test Milk 1L",
        "category": "dairy",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 7,
        "unit_type": "volume",
        "default_unit": "ml",
    }
    response = await client.post("/api/products", json=product_data)
    return response.json()


class TestListInventory:
    """Test GET /api/inventory endpoint."""

    async def test_list_inventory_empty_list(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/inventory should return empty list when no items exist."""
        response = await client.get("/api/inventory")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_list_inventory_returns_all_items(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """GET /api/inventory should return all inventory items."""
        # Create test inventory items
        today = date.today()
        item1 = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
            "location": "main_fridge",
        }
        item2 = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 250,
            "unit": "ml",
            "status": "opened",
            "expiry_date": str(today + timedelta(days=5)),
            "location": "main_fridge",
        }

        await client.post("/api/inventory", json=item1)
        await client.post("/api/inventory", json=item2)

        response = await client.get("/api/inventory")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 2

    async def test_list_inventory_filter_by_location(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """GET /api/inventory?location= should filter by location."""
        today = date.today()
        fridge_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
            "location": "main_fridge",
        }
        freezer_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 500,
            "unit": "g",
            "expiry_date": str(today + timedelta(days=90)),
            "location": "freezer",
        }

        await client.post("/api/inventory", json=fridge_item)
        await client.post("/api/inventory", json=freezer_item)

        response = await client.get("/api/inventory?location=freezer")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["location"] == "freezer"

    async def test_list_inventory_filter_by_status(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """GET /api/inventory?status= should filter by status."""
        today = date.today()
        sealed_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "status": "sealed",
            "expiry_date": str(today + timedelta(days=7)),
        }
        opened_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 250,
            "unit": "ml",
            "status": "opened",
            "expiry_date": str(today + timedelta(days=5)),
        }

        await client.post("/api/inventory", json=sealed_item)
        await client.post("/api/inventory", json=opened_item)

        response = await client.get("/api/inventory?status=opened")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["status"] == "opened"

    async def test_list_inventory_expiring_soon(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """GET /api/inventory?expiring_days= should filter by expiring soon."""
        today = date.today()
        expiring_soon = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=2)),
        }
        not_expiring = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 500,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=30)),
        }

        await client.post("/api/inventory", json=expiring_soon)
        await client.post("/api/inventory", json=not_expiring)

        # Get items expiring within 3 days
        response = await client.get("/api/inventory?expiring_days=3")

        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1


class TestGetInventoryItem:
    """Test GET /api/inventory/{id} endpoint."""

    async def test_get_inventory_item_returns_item(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """GET /api/inventory/{id} should return specific inventory item."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 750,
            "unit": "ml",
            "status": "opened",
            "expiry_date": str(today + timedelta(days=7)),
            "location": "main_fridge",
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        response = await client.get(f"/api/inventory/{created_item['id']}")

        assert response.status_code == 200
        item = response.json()
        assert item["current_quantity"] == "750.00"
        assert item["status"] == "opened"

    async def test_get_inventory_item_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/inventory/{id} should return 404 for non-existent item."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/inventory/{fake_uuid}")

        assert response.status_code == 404
        assert "detail" in response.json()


class TestCreateInventoryItem:
    """Test POST /api/inventory endpoint."""

    async def test_create_inventory_item_success(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """POST /api/inventory should create a new inventory item."""
        today = date.today()
        new_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "status": "sealed",
            "purchase_date": str(today),
            "expiry_date": str(today + timedelta(days=7)),
            "expiry_source": "calculated",
            "location": "main_fridge",
            "notes": "Fresh milk from store",
        }

        response = await client.post("/api/inventory", json=new_item)

        assert response.status_code == 201
        item = response.json()
        assert item["current_quantity"] == "1000.00"
        assert item["status"] == "sealed"
        assert "id" in item
        assert UUID(item["id"])  # Valid UUID

    async def test_create_inventory_item_minimal_fields(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """POST /api/inventory should work with only required fields."""
        today = date.today()
        minimal_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 500,
            "unit": "g",
            "expiry_date": str(today + timedelta(days=5)),
        }

        response = await client.post("/api/inventory", json=minimal_item)

        assert response.status_code == 201
        item = response.json()
        assert item["status"] == "sealed"  # Default
        assert item["location"] == "main_fridge"  # Default

    async def test_create_inventory_item_invalid_product(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/inventory should reject invalid product_master_id."""
        today = date.today()
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        invalid_item = {
            "product_master_id": fake_uuid,
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
        }

        response = await client.post("/api/inventory", json=invalid_item)

        assert response.status_code == 400

    async def test_create_inventory_item_missing_required_fields(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/inventory should reject requests with missing required fields."""
        incomplete_item = {
            "initial_quantity": 1000,
            # Missing product_master_id, current_quantity, unit, expiry_date
        }

        response = await client.post("/api/inventory", json=incomplete_item)

        assert response.status_code == 422  # Validation error


class TestUpdateInventoryItem:
    """Test PATCH /api/inventory/{id} endpoint."""

    async def test_update_inventory_item_success(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """PATCH /api/inventory/{id} should update inventory item fields."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        # Update it
        updates = {
            "current_quantity": 750,
            "status": "opened",
            "opened_date": str(today),
        }

        response = await client.patch(
            f"/api/inventory/{created_item['id']}", json=updates
        )

        assert response.status_code == 200
        item = response.json()
        assert item["current_quantity"] == "750.00"
        assert item["status"] == "opened"
        assert item["opened_date"] == str(today)

    async def test_update_inventory_item_location(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """PATCH /api/inventory/{id} should allow updating location."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 500,
            "unit": "g",
            "expiry_date": str(today + timedelta(days=90)),
            "location": "main_fridge",
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        updates = {"location": "freezer"}

        response = await client.patch(
            f"/api/inventory/{created_item['id']}", json=updates
        )

        assert response.status_code == 200
        item = response.json()
        assert item["location"] == "freezer"

    async def test_update_inventory_item_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/inventory/{id} should return 404 for non-existent item."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        updates = {"current_quantity": 500}

        response = await client.patch(f"/api/inventory/{fake_uuid}", json=updates)

        assert response.status_code == 404


class TestDeleteInventoryItem:
    """Test DELETE /api/inventory/{id} endpoint."""

    async def test_delete_inventory_item_success(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """DELETE /api/inventory/{id} should delete inventory item."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        # Delete it
        response = await client.delete(f"/api/inventory/{created_item['id']}")

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get(f"/api/inventory/{created_item['id']}")
        assert get_response.status_code == 404

    async def test_delete_inventory_item_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """DELETE /api/inventory/{id} should return 404 for non-existent item."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"/api/inventory/{fake_uuid}")

        assert response.status_code == 404


class TestConsumeInventoryItem:
    """Test POST /api/inventory/{id}/consume endpoint."""

    async def test_consume_full_item(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """POST /api/inventory/{id}/consume should reduce quantity by full amount."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "status": "sealed",
            "expiry_date": str(today + timedelta(days=7)),
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        # Consume entire item
        consume_data = {"quantity": 1000}

        response = await client.post(
            f"/api/inventory/{created_item['id']}/consume", json=consume_data
        )

        assert response.status_code == 200
        item = response.json()
        assert item["current_quantity"] == "0.00"
        assert item["status"] == "empty"

    async def test_consume_partial_item(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """POST /api/inventory/{id}/consume should reduce quantity partially."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "status": "sealed",
            "expiry_date": str(today + timedelta(days=7)),
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        # Consume half
        consume_data = {"quantity": 500}

        response = await client.post(
            f"/api/inventory/{created_item['id']}/consume", json=consume_data
        )

        assert response.status_code == 200
        item = response.json()
        assert item["current_quantity"] == "500.00"
        assert item["status"] == "partial"

    async def test_consume_opens_sealed_item(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """POST /api/inventory/{id}/consume should mark sealed item as opened."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 1000,
            "unit": "ml",
            "status": "sealed",
            "expiry_date": str(today + timedelta(days=7)),
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        # Consume small amount from sealed item
        consume_data = {"quantity": 250}

        response = await client.post(
            f"/api/inventory/{created_item['id']}/consume", json=consume_data
        )

        assert response.status_code == 200
        item = response.json()
        assert item["current_quantity"] == "750.00"
        assert item["status"] == "opened"
        assert item["opened_date"] == str(today)

    async def test_consume_more_than_available(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """POST /api/inventory/{id}/consume should reject consuming more than available."""
        today = date.today()
        item_data = {
            "product_master_id": test_product["id"],
            "initial_quantity": 1000,
            "current_quantity": 500,
            "unit": "ml",
            "expiry_date": str(today + timedelta(days=7)),
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        # Try to consume more than available
        consume_data = {"quantity": 1000}

        response = await client.post(
            f"/api/inventory/{created_item['id']}/consume", json=consume_data
        )

        assert response.status_code == 400
        assert "cannot consume" in response.json()["detail"].lower()

    async def test_consume_item_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/inventory/{id}/consume should return 404 for non-existent item."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        consume_data = {"quantity": 100}

        response = await client.post(
            f"/api/inventory/{fake_uuid}/consume", json=consume_data
        )

        assert response.status_code == 404
