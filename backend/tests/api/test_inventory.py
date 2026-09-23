"""Tests for Inventory CRUD API endpoints."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.db.session import get_db
from app.main import app
from app.models.consumption_log import ConsumptionLog


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
        "default_unit": "dl",
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
            "unit": "dl",
            "expiry_date": str(today + timedelta(days=7)),
            "location": "main_fridge",
        }
        item2 = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 250,
            "unit": "dl",
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
            "unit": "dl",
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
            "unit": "dl",
            "status": "sealed",
            "expiry_date": str(today + timedelta(days=7)),
        }
        opened_item = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 250,
            "unit": "dl",
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
            "unit": "dl",
            "expiry_date": str(today + timedelta(days=2)),
        }
        not_expiring = {
            "product_master_id": test_product["id"],
            "initial_quantity": 500,
            "current_quantity": 500,
            "unit": "dl",
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
            "unit": "dl",
            "status": "opened",
            "expiry_date": str(today + timedelta(days=7)),
            "location": "main_fridge",
        }

        create_response = await client.post("/api/inventory", json=item_data)
        created_item = create_response.json()

        response = await client.get(f"/api/inventory/{created_item['id']}")

        assert response.status_code == 200
        item = response.json()
        assert item["current_quantity"] == 750
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
            "unit": "dl",
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
        assert item["current_quantity"] == 1000
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
            "unit": "dl",
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
            "unit": "dl",
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
        assert item["current_quantity"] == 750
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
            "unit": "dl",
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
            "unit": "dl",
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
        assert item["current_quantity"] == 0
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
            "unit": "dl",
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
        assert item["current_quantity"] == 500
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
            "unit": "dl",
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
        assert item["current_quantity"] == 750
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
            "unit": "dl",
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


async def _create_item(client: AsyncClient, product_id: str, **overrides) -> dict:
    """Create an inventory item through the API and return its JSON body."""
    item = {
        "product_master_id": product_id,
        "initial_quantity": 1000,
        "current_quantity": 1000,
        "unit": "dl",
        "expiry_date": str(date.today() + timedelta(days=7)),
    }
    item.update(overrides)
    response = await client.post("/api/inventory", json=item)
    assert response.status_code == 201, response.text
    return response.json()


async def _logs_for(db: AsyncSession, item_id: str) -> list[ConsumptionLog]:
    result = await db.execute(
        select(ConsumptionLog)
        .where(ConsumptionLog.inventory_item_id == UUID(item_id))
        .order_by(ConsumptionLog.logged_at)
    )
    return list(result.scalars().all())


def _history(logs: list[ConsumptionLog]) -> list[tuple[str, float, float]]:
    """Each row as (action, how much it moved, what was left) - enough to replay the item."""
    return [
        (str(log.action), float(log.quantity_consumed), float(log.quantity_after))
        for log in logs
    ]


def _assert_product_fields(item: dict) -> None:
    assert item["product_name"] == "Test Milk 1L"
    assert item["category"] == "dairy"
    assert item["category_name"] == "Dairy & Eggs"
    assert item["category_icon"] == "\U0001f95b"


class TestInventoryResponseShape:
    """MVP-S1: product fields and numeric quantities on every inventory response."""

    async def test_create_response_includes_product_fields(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"])
        _assert_product_fields(item)

    async def test_list_and_get_include_product_fields(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        created = await _create_item(client, test_product["id"])

        listed = (await client.get("/api/inventory")).json()
        fetched = (await client.get(f"/api/inventory/{created['id']}")).json()

        assert len(listed) == 1
        _assert_product_fields(listed[0])
        _assert_product_fields(fetched)

    async def test_update_and_consume_include_product_fields(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        created = await _create_item(client, test_product["id"])

        updated = await client.patch(
            f"/api/inventory/{created['id']}", json={"location": "freezer"}
        )
        consumed = await client.post(
            f"/api/inventory/{created['id']}/consume", json={"quantity": 100}
        )

        assert updated.status_code == 200
        assert consumed.status_code == 200
        _assert_product_fields(updated.json())
        _assert_product_fields(consumed.json())

    async def test_quantities_are_json_numbers(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        created = await _create_item(
            client, test_product["id"], initial_quantity=1000, current_quantity=750.5
        )

        for body in (created, (await client.get("/api/inventory")).json()[0]):
            assert isinstance(body["initial_quantity"], int | float)
            assert isinstance(body["current_quantity"], int | float)
            assert body["current_quantity"] == 750.5


class TestInactiveItemsHidden:
    """MVP-S1: empty and discarded items are hidden from the default list."""

    async def _create_one_of_each(self, client: AsyncClient, product_id: str) -> dict:
        return {
            "sealed": await _create_item(client, product_id),
            "empty": await _create_item(
                client, product_id, current_quantity=0, status="empty"
            ),
            "discarded": await _create_item(client, product_id, status="discarded"),
        }

    async def test_default_list_hides_empty_and_discarded(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        items = await self._create_one_of_each(client, test_product["id"])

        response = await client.get("/api/inventory")

        assert response.status_code == 200
        assert [i["id"] for i in response.json()] == [items["sealed"]["id"]]

    async def test_include_inactive_returns_all(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        await self._create_one_of_each(client, test_product["id"])

        response = await client.get("/api/inventory?include_inactive=true")

        assert response.status_code == 200
        assert sorted(i["status"] for i in response.json()) == [
            "discarded",
            "empty",
            "sealed",
        ]

    async def test_explicit_status_filter_returns_inactive_items(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        items = await self._create_one_of_each(client, test_product["id"])

        response = await client.get("/api/inventory?status=empty")

        assert response.status_code == 200
        assert [i["id"] for i in response.json()] == [items["empty"]["id"]]


class TestListOrdering:
    """MVP-S2: a total, stable order so cards do not swap places between refetches."""

    async def test_equal_expiry_items_keep_creation_order(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        expiry = str(date.today() + timedelta(days=5))
        created = [
            (await _create_item(client, test_product["id"], expiry_date=expiry))["id"]
            for _ in range(4)
        ]

        first = [item["id"] for item in (await client.get("/api/inventory")).json()]

        # Consuming or editing rewrites the row, and Postgres then returns ties in a new
        # physical order unless the query breaks them explicitly.
        await client.post(
            f"/api/inventory/{created[0]}/consume", json={"quantity": 100}
        )
        await client.patch(f"/api/inventory/{created[1]}", json={"notes": "moved"})
        second = [item["id"] for item in (await client.get("/api/inventory")).json()]

        assert first == created
        assert second == created

    async def test_earlier_expiry_comes_first(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        later = await _create_item(
            client,
            test_product["id"],
            expiry_date=str(date.today() + timedelta(days=9)),
        )
        sooner = await _create_item(
            client,
            test_product["id"],
            expiry_date=str(date.today() + timedelta(days=2)),
        )

        ids = [item["id"] for item in (await client.get("/api/inventory")).json()]

        assert ids == [sooner["id"], later["id"]]


class TestConsumptionLogWrites:
    """MVP-S1: consume and discard write consumption_log rows."""

    async def test_partial_consume_logs_use_partial(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"])

        await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 250}
        )

        logs = await _logs_for(seeded_db, item["id"])
        assert [(log.action, float(log.quantity_consumed)) for log in logs] == [
            ("use_partial", 250.0)
        ]
        assert str(logs[0].product_master_id) == test_product["id"]

    async def test_full_consume_logs_use_full(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"], current_quantity=400)

        await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 400}
        )

        logs = await _logs_for(seeded_db, item["id"])
        assert [(log.action, float(log.quantity_consumed)) for log in logs] == [
            ("use_full", 400.0)
        ]

    async def test_rejected_consume_logs_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"], current_quantity=100)

        response = await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 500}
        )

        assert response.status_code == 400
        assert await _logs_for(seeded_db, item["id"]) == []

    async def test_discard_logs_once_with_remaining_quantity(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"], current_quantity=600)

        first = await client.patch(
            f"/api/inventory/{item['id']}", json={"status": "discarded"}
        )
        second = await client.patch(
            f"/api/inventory/{item['id']}", json={"status": "discarded"}
        )

        assert first.status_code == 200
        # The second used to be a silent 200 that deduped after the fact. A discarded item is
        # frozen now (H23), so it is refused outright - which also means the dedupe cannot be
        # raced, as two concurrent PATCHes both passing the old check could both log.
        assert second.status_code == 409
        logs = await _logs_for(seeded_db, item["id"])
        assert [(log.action, float(log.quantity_consumed)) for log in logs] == [
            ("discard", 600.0)
        ]

    async def test_non_status_update_logs_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"])

        await client.patch(f"/api/inventory/{item['id']}", json={"location": "pantry"})

        assert await _logs_for(seeded_db, item["id"]) == []


class TestConsumptionHistory:
    """H46: every change to an item's quantity leaves one row that can be read on its own."""

    async def _patch(self, client: AsyncClient, item_id: str, **fields) -> dict:
        response = await client.patch(f"/api/inventory/{item_id}", json=fields)
        assert response.status_code == 200, response.text
        return response.json()

    async def test_the_rows_replay_the_item(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """Consume, correct, throw away, bring back: four events, four rows."""
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )

        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 3})
        await self._patch(client, item["id"], current_quantity=5)
        await self._patch(client, item["id"], status="discarded")
        await self._patch(client, item["id"], status="opened")

        assert _history(await _logs_for(seeded_db, item["id"])) == [
            ("use_partial", 3.0, 7.0),
            ("correct", 2.0, 5.0),
            ("discard", 5.0, 0.0),
            ("restore", 5.0, 5.0),
        ]

    async def test_a_correction_upward_says_so_in_what_was_left(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=4
        )

        await self._patch(client, item["id"], current_quantity=6)

        assert _history(await _logs_for(seeded_db, item["id"])) == [
            ("correct", 2.0, 6.0)
        ]

    async def test_a_correction_to_the_same_amount_logs_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=4
        )

        await self._patch(
            client,
            item["id"],
            current_quantity=4,
            expiry_date=str(date.today() + timedelta(days=3)),
        )

        assert await _logs_for(seeded_db, item["id"]) == []

    async def test_throwing_away_an_empty_item_is_not_waste(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """It used to log a discard of 0, which nothing reading the log could make sense of."""
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 10})

        await self._patch(client, item["id"], status="discarded")

        assert _history(await _logs_for(seeded_db, item["id"])) == [
            ("use_full", 10.0, 0.0)
        ]

    async def test_bulk_discard_and_restore_log_both_ways(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=8
        )

        await client.post("/api/inventory/discard", json={"ids": [item["id"]]})
        await client.post("/api/inventory/restore", json={"ids": [item["id"]]})

        assert _history(await _logs_for(seeded_db, item["id"])) == [
            ("discard", 8.0, 0.0),
            ("restore", 8.0, 8.0),
        ]

    async def test_consumed_at_is_when_it_left_the_kitchen(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )
        assert item["consumed_at"] is None

        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 4})
        partly = (await client.get(f"/api/inventory/{item['id']}")).json()
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 6})
        finished = (await client.get(f"/api/inventory/{item['id']}")).json()
        binned = await self._patch(client, item["id"], status="discarded")

        assert partly["consumed_at"] is None
        assert finished["consumed_at"] is not None
        # Already gone before it went in the bin, so the moment it went stays the same
        assert binned["consumed_at"] == finished["consumed_at"]

    async def test_coming_back_clears_consumed_at(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )
        binned = await self._patch(client, item["id"], status="discarded")

        restored = await self._patch(client, item["id"], status="opened")

        assert binned["consumed_at"] is not None
        assert restored["consumed_at"] is None

    async def test_finding_some_left_after_all_clears_consumed_at(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=2
        )
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 2})

        corrected = await self._patch(client, item["id"], current_quantity=1)

        assert corrected["status"] != "empty"
        assert corrected["consumed_at"] is None


class TestCanonicalUnitsOnWrite:
    """MVP-U1: requests may use any known unit; stored and returned in dl | tsp | tbsp | g | pcs."""

    async def test_millilitres_are_stored_as_decilitres(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client,
            test_product["id"],
            unit="ml",
            initial_quantity=330,
            current_quantity=330,
        )
        assert (item["unit"], item["initial_quantity"], item["current_quantity"]) == (
            "dl",
            3.3,
            3.3,
        )

    async def test_kilograms_and_legacy_unit_convert(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        cheese = await _create_item(
            client,
            test_product["id"],
            unit="kg",
            initial_quantity=0.4,
            current_quantity=0.4,
        )
        eggs = await _create_item(
            client,
            test_product["id"],
            unit="unit",
            initial_quantity=6,
            current_quantity=6,
        )
        spice = await _create_item(
            client,
            test_product["id"],
            unit="tbsp",
            initial_quantity=3,
            current_quantity=3,
        )
        assert (cheese["unit"], cheese["initial_quantity"]) == ("g", 400)
        assert (eggs["unit"], eggs["initial_quantity"]) == ("pcs", 6)
        assert (spice["unit"], spice["initial_quantity"]) == ("tbsp", 3)

    async def test_unknown_unit_is_rejected(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        response = await client.post(
            "/api/inventory",
            json={
                "product_master_id": test_product["id"],
                "initial_quantity": 12,
                "current_quantity": 12,
                "unit": "oz",
                "expiry_date": str(date.today() + timedelta(days=7)),
            },
        )
        assert response.status_code == 422


class TestItemCorrections:
    """MVP-S4: the edit sheet corrects quantity, expiry and location, marks gone, deletes."""

    async def _patch(self, client: AsyncClient, item_id: str, **fields) -> dict:
        response = await client.patch(f"/api/inventory/{item_id}", json=fields)
        assert response.status_code == 200, response.text
        return response.json()

    async def test_delete_removes_the_item_but_keeps_what_it_wasted(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """The record outlives the item (2026-09-22): metrics must not miss deleted rows."""
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 5})
        assert len(await _logs_for(seeded_db, item["id"])) == 1

        response = await client.delete(f"/api/inventory/{item['id']}")

        assert response.status_code == 204
        assert (await client.get(f"/api/inventory/{item['id']}")).status_code == 404
        # Detached from the item it can no longer point at, and still readable on its own
        assert await _logs_for(seeded_db, item["id"]) == []
        (row,) = (await client.get("/api/consumption-log")).json()
        assert (row["inventory_item_id"], row["item_status"]) == (None, None)
        assert (row["quantity_consumed"], row["unit"]) == (5.0, "dl")

    async def test_delete_after_discard_keeps_the_waste_row(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"])
        await self._patch(client, item["id"], status="discarded")

        response = await client.delete(f"/api/inventory/{item['id']}")

        assert response.status_code == 204
        rows = (await client.get("/api/consumption-log")).json()
        assert [(r["action"], r["item_status"]) for r in rows] == [("discard", None)]

    async def test_correcting_to_zero_empties_and_hides_the_item(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )

        body = await self._patch(client, item["id"], current_quantity=0)

        assert body["status"] == "empty"
        listed = (await client.get("/api/inventory")).json()
        assert item["id"] not in [i["id"] for i in listed]

    @pytest.mark.parametrize(
        ("quantity", "status"), [(4, "partial"), (9, "opened"), (10, "sealed")]
    )
    async def test_correcting_below_full_follows_the_consume_rules(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        test_product: dict,
        quantity: int,
        status: str,
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )

        body = await self._patch(client, item["id"], current_quantity=quantity)

        assert body["status"] == status
        assert (body["opened_date"] is not None) == (status != "sealed")
        assert body["initial_quantity"] == 10

    async def test_correcting_above_full_raises_the_full_amount(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )

        body = await self._patch(client, item["id"], current_quantity=15)

        assert (body["initial_quantity"], body["current_quantity"]) == (15, 15)
        # Still sealed because this pack was never opened - `opened_date` is unset (H23).
        assert body["status"] == "sealed"

    async def test_correcting_an_opened_item_above_full_stops_lying(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """The stale label: 200/1000 `partial` corrected to 1200 used to stay `partial`.

        `initial_quantity` is raised first, so the old "below full" test read false and the
        status was never revisited. It reads `opened` now - full again, but a jar does not
        re-seal itself.
        """
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 8})

        body = await self._patch(client, item["id"], current_quantity=12)

        assert (body["initial_quantity"], body["current_quantity"]) == (12, 12)
        assert body["status"] == "opened"

    async def test_correcting_an_empty_item_makes_it_active_again(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 10})

        body = await self._patch(client, item["id"], current_quantity=3)

        assert body["status"] == "partial"
        listed = (await client.get("/api/inventory")).json()
        assert item["id"] in [i["id"] for i in listed]

    async def test_a_correction_is_logged_but_not_as_consumption(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """It used to write nothing, so the log could not explain where the 8 went (H46)."""
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )

        await self._patch(client, item["id"], current_quantity=2)

        assert _history(await _logs_for(seeded_db, item["id"])) == [
            ("correct", 8.0, 2.0)
        ]

    async def test_the_quantity_rules_win_over_an_explicit_status(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """The reverse of what this pinned before H23, and deliberately.

        A client used to be able to name any status and have the rules skipped entirely -
        which is also how `discarded` could become `sealed`. The status is derived from what
        happened now, so 2 of 10 left is `partial` whatever the body asked for.
        """
        item = await _create_item(
            client, test_product["id"], initial_quantity=10, current_quantity=10
        )

        body = await self._patch(
            client, item["id"], current_quantity=2, status="opened"
        )

        assert body["status"] == "partial"

    async def test_new_expiry_date_is_marked_manual(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"])
        assert item["expiry_source"] == "calculated"

        body = await self._patch(client, item["id"], expiry_date="2030-01-31")

        assert (body["expiry_date"], body["expiry_source"]) == ("2030-01-31", "manual")

    async def test_given_expiry_source_is_kept(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"])

        body = await self._patch(
            client, item["id"], expiry_date="2030-01-31", expiry_source="scanned"
        )

        assert body["expiry_source"] == "scanned"

    async def test_location_change_keeps_expiry_source(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """Moving something does not rewrite how its date was arrived at.

        This used to move the item to the **freezer**, which is now the one exception:
        DEC-10 was settled on 2026-09-19 and freezing re-dates the item and marks it
        `frozen` (Q12). The assertion was pinning the behaviour that decision reversed,
        so the move is to the pantry now and the freezer has its own tests in
        `TestFrozenClock` - including that every *other* location still changes nothing.
        """
        item = await _create_item(client, test_product["id"])

        body = await self._patch(client, item["id"], location="pantry")

        assert (body["location"], body["expiry_source"]) == ("pantry", "calculated")

    @pytest.mark.parametrize(
        "fields",
        [{"location": "garage"}, {"status": "gone"}, {"expiry_source": "guess"}],
    )
    async def test_unknown_values_are_rejected(
        self,
        client: AsyncClient,
        seeded_db: AsyncSession,
        test_product: dict,
        fields: dict,
    ) -> None:
        item = await _create_item(client, test_product["id"])

        response = await client.patch(f"/api/inventory/{item['id']}", json=fields)

        assert response.status_code == 422


class TestFrozenClock:
    """Q12/DEC-10: putting something in the freezer restarts its clock on a longer one.

    Mince frozen on the day it was bought used to read expired six days later, because the
    expiry came from the product's fridge shelf life and moving the item changed nothing.
    The edit sheet has always allowed the move, so the wrong answer was already reachable.
    """

    PRODUCT = {
        "canonical_name": "Ground beef",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 5,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def _stock(self, client: AsyncClient, product_id: str, **overrides) -> dict:
        body = {
            "product_master_id": product_id,
            "initial_quantity": 400,
            "current_quantity": 400,
            "unit": "g",
            "purchase_date": "2026-09-01",
            "expiry_date": "2026-09-06",
            "expiry_source": "calculated",
            "location": "main_fridge",
            **overrides,
        }
        response = await client.post("/api/inventory", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    async def test_moving_it_to_the_freezer_re_dates_it(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])

        moved = (
            await client.patch(
                f"/api/inventory/{item['id']}", json={"location": "freezer"}
            )
        ).json()

        # meat freezes for 180 days, counted from the day it goes in - not from purchase
        assert moved["expiry_date"] == (date.today() + timedelta(days=180)).isoformat()
        assert moved["expiry_source"] == "frozen"

    async def test_a_frozen_date_survives_a_shelf_life_correction(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """The half that makes Q12's two PRs compose.

        Without `frozen` as its own source the recompute would treat the item as
        `calculated` and thaw the clock the next time the catalog learned anything.
        """
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])
        frozen = (
            await client.patch(
                f"/api/inventory/{item['id']}", json={"location": "freezer"}
            )
        ).json()

        await client.patch(
            f"/api/products/{product['id']}", json={"default_shelf_life_days": 2}
        )

        after = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert after["expiry_date"] == frozen["expiry_date"]
        assert after["expiry_source"] == "frozen"

    async def test_a_date_the_cook_names_in_the_same_edit_wins(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])

        moved = (
            await client.patch(
                f"/api/inventory/{item['id']}",
                json={"location": "freezer", "expiry_date": "2026-11-01"},
            )
        ).json()

        assert moved["expiry_date"] == "2026-11-01"
        assert moved["expiry_source"] == "manual"

    async def test_a_category_that_does_not_freeze_is_left_alone(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Nothing useful happens to a frozen bottle of squash."""
        product = (
            await client.post(
                "/api/products",
                json={
                    **self.PRODUCT,
                    "canonical_name": "Orange juice",
                    "category": "beverages",
                    "storage_type": "refrigerator",
                    "unit_type": "volume",
                    "default_unit": "dl",
                },
            )
        ).json()
        item = await self._stock(client, product["id"], unit="dl")

        moved = (
            await client.patch(
                f"/api/inventory/{item['id']}", json={"location": "freezer"}
            )
        ).json()

        assert moved["expiry_date"] == "2026-09-06"
        assert moved["expiry_source"] == "calculated"

    async def test_moving_it_anywhere_else_changes_no_date(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])

        moved = (
            await client.patch(
                f"/api/inventory/{item['id']}", json={"location": "pantry"}
            )
        ).json()

        assert moved["expiry_date"] == "2026-09-06"
        assert moved["expiry_source"] == "calculated"

    async def test_an_item_already_in_the_freezer_is_not_re_dated_again(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Otherwise every unrelated edit would quietly extend it."""
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"], location="freezer")

        moved = (
            await client.patch(
                f"/api/inventory/{item['id']}",
                json={"location": "freezer", "current_quantity": 200},
            )
        ).json()

        assert moved["expiry_date"] == "2026-09-06"


class TestDiscardFreezesTheItem:
    """H23: a thing in the bin is not in the kitchen.

    Before this, the discard was logged and the quantity left alone, and no writer checked the
    status first - so consuming a discarded item walked it straight back into the list, which
    was also the only way to undo a mis-tap.
    """

    async def _discarded(self, client: AsyncClient, product_id: str) -> dict:
        item = await _create_item(
            client, product_id, initial_quantity=10, current_quantity=10
        )
        body = await client.patch(
            f"/api/inventory/{item['id']}", json={"status": "discarded"}
        )
        assert body.status_code == 200, body.text
        return body.json()

    async def test_consuming_a_discarded_item_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await self._discarded(client, test_product["id"])

        response = await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 1}
        )

        assert response.status_code == 409
        assert "thrown away" in response.json()["detail"].lower()

    async def test_correcting_a_discarded_item_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await self._discarded(client, test_product["id"])

        response = await client.patch(
            f"/api/inventory/{item['id']}", json={"current_quantity": 5}
        )

        assert response.status_code == 409

    async def test_it_stays_out_of_the_list(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await self._discarded(client, test_product["id"])
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 1})

        listed = (await client.get("/api/inventory")).json()

        assert item["id"] not in [i["id"] for i in listed]

    async def test_discarding_twice_logs_once(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """The second one is refused outright now, rather than deduped after the fact."""
        item = await self._discarded(client, test_product["id"])

        again = await client.patch(
            f"/api/inventory/{item['id']}", json={"status": "discarded"}
        )

        assert again.status_code == 409
        logs = await _logs_for(seeded_db, item["id"])
        assert [log.action for log in logs] == ["discard"]

    async def test_a_mis_tap_can_be_undone(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """Freezing the item would otherwise make Mark as gone permanent.

        No screen shows an inactive item yet, so nothing calls this from the iPad - but the
        way back exists, and it comes back opened rather than sealed, because it was in the
        bin.
        """
        item = await self._discarded(client, test_product["id"])

        restored = await client.patch(
            f"/api/inventory/{item['id']}", json={"status": "opened"}
        )

        assert restored.status_code == 200
        assert restored.json()["status"] == "opened"
        listed = (await client.get("/api/inventory")).json()
        assert item["id"] in [i["id"] for i in listed]


class TestConsumeBounds:
    """The three bounds H23 asks for, at the door rather than in the data."""

    async def test_an_amount_that_rounds_to_nothing_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """Quantities store to two decimals; a thousandth of a decilitre is not a helping."""
        item = await _create_item(client, test_product["id"])

        response = await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 0.004}
        )

        assert response.status_code == 400
        assert "rounds to nothing" in response.json()["detail"]
        assert await _logs_for(seeded_db, item["id"]) == []

    async def test_a_unit_of_the_same_kind_is_converted(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """A caller that cannot see the item may say what it means: 0.2 l is 2 dl."""
        item = await _create_item(
            client,
            test_product["id"],
            initial_quantity=10,
            current_quantity=10,
            unit="dl",
        )

        response = await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 0.2, "unit": "l"}
        )

        assert response.status_code == 200
        assert response.json()["current_quantity"] == 8

    async def test_a_unit_of_a_different_kind_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """Subtracting 200 g from a count of twelve apples is a mistake, not a conversion."""
        item = await _create_item(
            client,
            test_product["id"],
            initial_quantity=12,
            current_quantity=12,
            unit="pcs",
        )

        response = await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 200, "unit": "g"}
        )

        assert response.status_code == 400
        assert "measured in" in response.json()["detail"]

    async def test_omitting_the_unit_means_the_items_own(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client,
            test_product["id"],
            initial_quantity=10,
            current_quantity=10,
            unit="dl",
        )

        response = await client.post(
            f"/api/inventory/{item['id']}/consume", json={"quantity": 2}
        )

        assert response.json()["current_quantity"] == 8


class TestCreateRefusesIncoherentRows:
    """A row that could never have come about is refused rather than stored (H23)."""

    async def test_current_above_initial(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        response = await client.post(
            "/api/inventory",
            json={
                "product_master_id": test_product["id"],
                "initial_quantity": 5,
                "current_quantity": 10,
                "unit": "dl",
                "expiry_date": str(date.today() + timedelta(days=7)),
            },
        )

        assert response.status_code == 422

    async def test_expiry_before_purchase(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        response = await client.post(
            "/api/inventory",
            json={
                "product_master_id": test_product["id"],
                "initial_quantity": 5,
                "current_quantity": 5,
                "unit": "dl",
                "purchase_date": str(date.today()),
                "expiry_date": str(date.today() - timedelta(days=1)),
            },
        )

        assert response.status_code == 422

    async def test_the_ordinary_row_still_goes_in(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(
            client,
            test_product["id"],
            initial_quantity=5,
            current_quantity=3,
            purchase_date=str(date.today() - timedelta(days=1)),
        )

        assert item["current_quantity"] == 3


class TestListFiltersAreAVocabulary:
    """H24 closed the request bodies and left the query string open.

    `?status=banana` used to answer `200 []`, which reads as "there are no such items" rather
    than "there is no such status" - a distinction that matters to a client which cannot see
    the schema. The screen that lists thrown-away items filters on exactly this.
    """

    @pytest.mark.parametrize(
        ("param", "value"),
        [("status", "banana"), ("location", "under_the_sink")],
    )
    async def test_a_value_outside_the_vocabulary_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession, param, value
    ) -> None:
        response = await client.get(f"/api/inventory?{param}={value}")

        assert response.status_code == 422
        (problem,) = response.json()["detail"]
        assert problem["loc"][-1] == param

    async def test_the_real_values_still_work(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        item = await _create_item(client, test_product["id"], location="freezer")
        await client.patch(f"/api/inventory/{item['id']}", json={"status": "discarded"})

        # `status` overrides the default hiding of inactive items, so this is how a screen
        # would list what has been thrown away.
        gone = (await client.get("/api/inventory?status=discarded")).json()
        assert [i["id"] for i in gone] == [item["id"]]

        by_location = (await client.get("/api/inventory?location=freezer")).json()
        assert by_location == []


class TestBulkDiscardAndRestore:
    """Clearing a shelf of expired food, and taking it back.

    One transaction rather than a PATCH each: thirteen items were thirteen round trips,
    thirteen transactions and thirteen broadcasts, and a failure half way left the shelf half
    cleared with no way to tell.
    """

    async def _items(
        self, client: AsyncClient, product_id: str, count: int
    ) -> list[dict]:
        return [
            await _create_item(
                client, product_id, initial_quantity=10, current_quantity=10
            )
            for _ in range(count)
        ]

    async def test_it_throws_them_all_away_at_once(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        items = await self._items(client, test_product["id"], 3)

        response = await client.post(
            "/api/inventory/discard", json={"ids": [i["id"] for i in items]}
        )

        assert response.status_code == 200
        assert response.json() == {"changed": 3, "refused": 0, "missing": 0}

        listed = (await client.get("/api/inventory")).json()
        assert listed == []

    async def test_the_waste_log_gets_one_row_each(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """The whole reason the operator chose `discarded` over `empty` for a clear."""
        items = await self._items(client, test_product["id"], 2)

        await client.post(
            "/api/inventory/discard", json={"ids": [i["id"] for i in items]}
        )

        for item in items:
            logs = await _logs_for(seeded_db, item["id"])
            assert [(log.action, float(log.quantity_consumed)) for log in logs] == [
                ("discard", 10.0)
            ]

    async def test_something_already_gone_is_refused_not_logged_twice(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        """A cook clearing a shelf should not have it all fail because one had gone already."""
        items = await self._items(client, test_product["id"], 2)
        await client.patch(
            f"/api/inventory/{items[0]['id']}", json={"status": "discarded"}
        )

        response = await client.post(
            "/api/inventory/discard", json={"ids": [i["id"] for i in items]}
        )

        assert response.json() == {"changed": 1, "refused": 1, "missing": 0}
        logs = await _logs_for(seeded_db, items[0]["id"])
        assert len(logs) == 1

    async def test_an_id_that_matches_nothing_is_counted(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        (item,) = await self._items(client, test_product["id"], 1)

        response = await client.post(
            "/api/inventory/discard", json={"ids": [item["id"], str(uuid4())]}
        )

        assert response.json() == {"changed": 1, "refused": 0, "missing": 1}

    async def test_restore_brings_back_exactly_what_went_in(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        items = await self._items(client, test_product["id"], 3)
        ids = [i["id"] for i in items]
        await client.post("/api/inventory/discard", json={"ids": ids})

        response = await client.post("/api/inventory/restore", json={"ids": ids})

        assert response.json() == {"changed": 3, "refused": 0, "missing": 0}
        listed = (await client.get("/api/inventory")).json()
        # Back as `opened`, never `sealed`: they were in the bin (H23).
        assert sorted(i["id"] for i in listed) == sorted(ids)
        assert {i["status"] for i in listed} == {"opened"}

    async def test_restoring_something_finished_keeps_it_empty(
        self, client: AsyncClient, seeded_db: AsyncSession, test_product: dict
    ) -> None:
        (item,) = await self._items(client, test_product["id"], 1)
        await client.post(f"/api/inventory/{item['id']}/consume", json={"quantity": 10})
        await client.patch(f"/api/inventory/{item['id']}", json={"status": "discarded"})

        await client.post("/api/inventory/restore", json={"ids": [item["id"]]})

        back = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert back["status"] == "empty"
        # Nothing was thrown away and nothing came back, so only the helping is history
        assert _history(await _logs_for(seeded_db, item["id"])) == [
            ("use_full", 10.0, 0.0)
        ]

    async def test_an_empty_list_is_refused_at_the_door(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post("/api/inventory/discard", json={"ids": []})

        assert response.status_code == 422
