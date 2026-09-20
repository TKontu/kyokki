"""Tests for shopping list API endpoints."""

from datetime import UTC
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem


@pytest.mark.asyncio
class TestShoppingListAPI:
    """Test shopping list CRUD operations."""

    async def test_create_shopping_item_free_text(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test creating a free-text shopping list item."""
        response = await client.post(
            "/api/shopping/",
            json={
                "name": "Bananas",
                "quantity": "6",
                "unit": "pcs",
                "priority": "normal",
                "source": "manual",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Bananas"
        assert data["quantity"] == 6
        assert data["unit"] == "pcs"
        assert data["priority"] == "normal"
        assert data["source"] == "manual"
        assert data["is_purchased"] is False
        assert data["product_master_id"] is None
        assert "id" in data
        assert "added_at" in data

    async def test_create_shopping_item_with_product(
        self,
        client: AsyncClient,
        test_db: AsyncSession,
        sample_product: ProductMaster,
    ):
        """Test creating a shopping list item linked to a product."""
        response = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": str(sample_product.id),
                "name": sample_product.canonical_name,
                "quantity": "2",
                "unit": sample_product.default_unit,
                "priority": "urgent",
                "source": "auto_restock",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["product_master_id"] == str(sample_product.id)
        assert data["priority"] == "urgent"
        assert data["source"] == "auto_restock"

    async def test_create_shopping_item_invalid_priority(self, client: AsyncClient):
        """Test creating item with invalid priority fails."""
        response = await client.post(
            "/api/shopping/",
            json={
                "name": "Test Item",
                "quantity": "1",
                "unit": "pcs",
                "priority": "super_urgent",  # Invalid
                "source": "manual",
            },
        )

        assert response.status_code == 422
        # The refusal moved from a hand-rolled check in the endpoint to the schema (H24), so
        # the body is Pydantic's structured detail rather than one string. Same status, and
        # it still names the field and what is allowed.
        (problem,) = response.json()["detail"]
        assert problem["loc"][-1] == "priority"
        assert "urgent" in problem["msg"]

    async def test_create_shopping_item_invalid_source(self, client: AsyncClient):
        """Test creating item with invalid source fails."""
        response = await client.post(
            "/api/shopping/",
            json={
                "name": "Test Item",
                "quantity": "1",
                "unit": "pcs",
                "priority": "normal",
                "source": "amazon",  # Invalid
            },
        )

        assert response.status_code == 422
        (problem,) = response.json()["detail"]
        assert problem["loc"][-1] == "source"
        assert "manual" in problem["msg"]

    async def test_get_shopping_list(self, client: AsyncClient, test_db: AsyncSession):
        """Test getting all shopping list items."""
        # Create some items
        items = [
            ShoppingListItem(
                name="Milk",
                quantity=Decimal("2"),
                unit="L",
                priority="urgent",
                source="manual",
            ),
            ShoppingListItem(
                name="Bread",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
            ),
            ShoppingListItem(
                name="Eggs",
                quantity=Decimal("12"),
                unit="pcs",
                priority="low",
                source="manual",
                is_purchased=True,
            ),
        ]
        for item in items:
            test_db.add(item)
        await test_db.commit()

        # Get list (should exclude purchased by default)
        response = await client.get("/api/shopping/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # Only unpurchased items
        assert data[0]["name"] == "Milk"  # Urgent first
        assert data[1]["name"] == "Bread"

    async def test_get_shopping_list_include_purchased(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test getting shopping list with purchased items."""
        items = [
            ShoppingListItem(
                name="Item 1",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
            ),
            ShoppingListItem(
                name="Item 2",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
                is_purchased=True,
            ),
        ]
        for item in items:
            test_db.add(item)
        await test_db.commit()

        response = await client.get("/api/shopping/?include_purchased=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_shopping_list_filter_priority(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test filtering shopping list by priority."""
        items = [
            ShoppingListItem(
                name="Urgent Item",
                quantity=Decimal("1"),
                unit="pcs",
                priority="urgent",
                source="manual",
            ),
            ShoppingListItem(
                name="Normal Item",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
            ),
        ]
        for item in items:
            test_db.add(item)
        await test_db.commit()

        response = await client.get("/api/shopping/?priority=urgent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Urgent Item"

    async def test_get_urgent_items(self, client: AsyncClient, test_db: AsyncSession):
        """Test getting only urgent items."""
        items = [
            ShoppingListItem(
                name="Urgent 1",
                quantity=Decimal("1"),
                unit="pcs",
                priority="urgent",
                source="manual",
            ),
            ShoppingListItem(
                name="Urgent 2",
                quantity=Decimal("1"),
                unit="pcs",
                priority="urgent",
                source="manual",
            ),
            ShoppingListItem(
                name="Normal",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
            ),
        ]
        for item in items:
            test_db.add(item)
        await test_db.commit()

        response = await client.get("/api/shopping/urgent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(item["priority"] == "urgent" for item in data)

    async def test_get_shopping_item(self, client: AsyncClient, test_db: AsyncSession):
        """Test getting a specific shopping item."""
        item = ShoppingListItem(
            name="Test Item",
            quantity=Decimal("1"),
            unit="pcs",
            priority="normal",
            source="manual",
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.get(f"/api/shopping/{item.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(item.id)
        assert data["name"] == "Test Item"

    async def test_get_shopping_item_not_found(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test getting non-existent item returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/shopping/{fake_id}")

        assert response.status_code == 404

    async def test_update_shopping_item(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test updating a shopping item."""
        item = ShoppingListItem(
            name="Original Name",
            quantity=Decimal("1"),
            unit="pcs",
            priority="normal",
            source="manual",
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.patch(
            f"/api/shopping/{item.id}",
            json={
                "name": "Updated Name",
                "quantity": "5",
                "priority": "urgent",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["quantity"] == 5
        assert data["priority"] == "urgent"

    async def test_update_shopping_item_invalid_priority(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test updating with invalid priority fails."""
        item = ShoppingListItem(
            name="Test",
            quantity=Decimal("1"),
            unit="pcs",
            priority="normal",
            source="manual",
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.patch(
            f"/api/shopping/{item.id}",
            json={"priority": "invalid"},
        )

        assert response.status_code == 422

    async def test_mark_item_purchased(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test marking an item as purchased."""
        item = ShoppingListItem(
            name="Test Item",
            quantity=Decimal("1"),
            unit="pcs",
            priority="normal",
            source="manual",
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.post(f"/api/shopping/{item.id}/purchase")

        assert response.status_code == 200
        data = response.json()
        assert data["is_purchased"] is True
        assert data["purchased_at"] is not None

    async def test_mark_item_unpurchased(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test marking a purchased item as unpurchased."""
        from datetime import datetime

        item = ShoppingListItem(
            name="Test Item",
            quantity=Decimal("1"),
            unit="pcs",
            priority="normal",
            source="manual",
            is_purchased=True,
            purchased_at=datetime.now(UTC),
        )
        test_db.add(item)
        await test_db.commit()

        response = await client.post(
            f"/api/shopping/{item.id}/purchase?purchased=false"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_purchased"] is False
        assert data["purchased_at"] is None

    async def test_delete_shopping_item(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test deleting a shopping item."""
        item = ShoppingListItem(
            name="Test Item",
            quantity=Decimal("1"),
            unit="pcs",
            priority="normal",
            source="manual",
        )
        test_db.add(item)
        await test_db.commit()
        item_id = item.id

        response = await client.delete(f"/api/shopping/{item_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = await client.get(f"/api/shopping/{item_id}")
        assert get_response.status_code == 404

    async def test_delete_all_purchased(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Test deleting all purchased items."""
        items = [
            ShoppingListItem(
                name="Unpurchased",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
            ),
            ShoppingListItem(
                name="Purchased 1",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
                is_purchased=True,
            ),
            ShoppingListItem(
                name="Purchased 2",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
                is_purchased=True,
            ),
        ]
        for item in items:
            test_db.add(item)
        await test_db.commit()

        response = await client.delete("/api/shopping/purchased/all")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 2

        # Verify only unpurchased remains
        list_response = await client.get("/api/shopping/")
        assert len(list_response.json()) == 1
        assert list_response.json()[0]["name"] == "Unpurchased"

    async def test_pagination(self, client: AsyncClient, test_db: AsyncSession):
        """Test pagination of shopping list."""
        # Create 15 items
        for i in range(15):
            item = ShoppingListItem(
                name=f"Item {i}",
                quantity=Decimal("1"),
                unit="pcs",
                priority="normal",
                source="manual",
            )
            test_db.add(item)
        await test_db.commit()

        # Get first page
        response = await client.get("/api/shopping/?skip=0&limit=10")
        assert response.status_code == 200
        assert len(response.json()) == 10

        # Get second page
        response = await client.get("/api/shopping/?skip=10&limit=10")
        assert response.status_code == 200
        assert len(response.json()) == 5


@pytest.mark.asyncio
class TestShoppingCanonicalUnits:
    """MVP-U1: shopping list quantities convert to canonical units."""

    async def test_litres_become_decilitres(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.post(
            "/api/shopping/",
            json={"name": "Milk", "quantity": "1.5", "unit": "l"},
        )
        assert response.status_code == 201
        assert (response.json()["quantity"], response.json()["unit"]) == (15, "dl")

    async def test_update_with_unit_converts(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        created = await client.post(
            "/api/shopping/", json={"name": "Flour", "quantity": "1", "unit": "pcs"}
        )
        item_id = created.json()["id"]

        response = await client.patch(
            f"/api/shopping/{item_id}", json={"quantity": "2", "unit": "kg"}
        )

        assert (response.json()["quantity"], response.json()["unit"]) == (2000, "g")

    async def test_unknown_unit_is_rejected(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.post(
            "/api/shopping/", json={"name": "Syrup", "quantity": "1", "unit": "gallon"}
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestShoppingIntegrityErrors:
    """Every shopping write went through CRUDBase, which commits inside the crud
    call, with no handler above it - so a constraint violation was a 500 (H05)."""

    async def test_unknown_product_answers_400(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        response = await client.post(
            "/api/shopping/",
            json={
                "product_master_id": "00000000-0000-0000-0000-000000000000",
                "name": "Ghost",
                "quantity": "1",
                "unit": "pcs",
                "priority": "normal",
                "source": "manual",
            },
        )

        assert response.status_code == 400
        assert "Key (" not in response.json()["detail"]

    async def test_updating_onto_an_unknown_product_answers_400(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        created = await client.post(
            "/api/shopping/",
            json={
                "name": "Bananas",
                "quantity": "6",
                "unit": "pcs",
                "priority": "normal",
                "source": "manual",
            },
        )
        assert created.status_code == 201

        response = await client.patch(
            f"/api/shopping/{created.json()['id']}",
            json={"product_master_id": "00000000-0000-0000-0000-000000000000"},
        )

        assert response.status_code == 400
