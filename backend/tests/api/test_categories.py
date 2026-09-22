"""Tests for Category CRUD API endpoints."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestListCategories:
    """Test GET /api/categories endpoint."""

    async def test_list_categories_returns_all_categories(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/categories should return all categories."""
        response = await client.get("/api/categories")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 10  # We have 12 seed categories

    async def test_list_categories_includes_required_fields(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Each category should include all required fields."""
        response = await client.get("/api/categories")

        assert response.status_code == 200
        categories = response.json()
        assert len(categories) > 0

        # Check first category has all fields
        category = categories[0]
        assert "id" in category
        assert "display_name" in category
        assert "default_shelf_life_days" in category
        assert "sort_order" in category

    async def test_list_categories_sorted_by_sort_order(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Categories should be sorted by sort_order."""
        response = await client.get("/api/categories")

        assert response.status_code == 200
        categories = response.json()

        # Verify they're sorted by sort_order
        sort_orders = [cat["sort_order"] for cat in categories]
        assert sort_orders == sorted(sort_orders)


class TestGetCategory:
    """Test GET /api/categories/{id} endpoint."""

    async def test_get_category_returns_category(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/categories/{id} should return specific category."""
        response = await client.get("/api/categories/meat")

        assert response.status_code == 200
        category = response.json()
        assert category["id"] == "meat"
        assert category["display_name"] == "Meat & Poultry"
        assert category["default_shelf_life_days"] == 5

    async def test_get_category_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/categories/{id} should return 404 for non-existent category."""
        response = await client.get("/api/categories/nonexistent")

        assert response.status_code == 404
        assert "detail" in response.json()


class TestCreateCategory:
    """Test POST /api/categories endpoint."""

    async def test_create_category_success(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/categories should create a new category."""
        new_category = {
            "id": "spices",
            "display_name": "Spices & Herbs",
            "icon": "🌿",
            "default_shelf_life_days": 180,
            "sort_order": 130,
        }

        response = await client.post("/api/categories", json=new_category)

        assert response.status_code == 201
        category = response.json()
        assert category["id"] == "spices"
        assert category["display_name"] == "Spices & Herbs"

    async def test_create_category_duplicate_id(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/categories should return 409 for duplicate ID.

        It answered 400 while the router caught IntegrityError by hand and called
        every integrity error a duplicate; handle_integrity_errors classifies it.
        """
        duplicate_category = {
            "id": "meat",  # Already exists in seed data
            "display_name": "Duplicate Meat",
            "default_shelf_life_days": 10,
            "sort_order": 999,
        }

        response = await client.post("/api/categories", json=duplicate_category)

        assert response.status_code == 409
        assert "detail" in response.json()

    async def test_create_category_invalid_shelf_life(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/categories should reject invalid shelf life values."""
        invalid_category = {
            "id": "invalid",
            "display_name": "Invalid Category",
            "default_shelf_life_days": 0,  # Must be > 0
            "sort_order": 999,
        }

        response = await client.post("/api/categories", json=invalid_category)

        assert response.status_code == 422  # Validation error

    async def test_create_category_missing_required_fields(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/categories should reject requests with missing required fields."""
        incomplete_category = {
            "id": "incomplete",
            # Missing display_name and default_shelf_life_days
        }

        response = await client.post("/api/categories", json=incomplete_category)

        assert response.status_code == 422  # Validation error


class TestUpdateCategory:
    """Test PATCH /api/categories/{id} endpoint."""

    async def test_update_category_success(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/categories/{id} should update category fields."""
        updates = {
            "display_name": "Updated Meat Name",
            "default_shelf_life_days": 7,
        }

        response = await client.patch("/api/categories/meat", json=updates)

        assert response.status_code == 200
        category = response.json()
        assert category["display_name"] == "Updated Meat Name"
        assert category["default_shelf_life_days"] == 7
        assert category["id"] == "meat"  # ID should not change

    async def test_update_category_partial_update(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/categories/{id} should allow partial updates."""
        updates = {"icon": "🥩🍗"}  # Only update icon

        response = await client.patch("/api/categories/meat", json=updates)

        assert response.status_code == 200
        category = response.json()
        assert category["icon"] == "🥩🍗"
        assert category["display_name"] == "Meat & Poultry"  # Unchanged

    async def test_update_category_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/categories/{id} should return 404 for non-existent category."""
        updates = {"display_name": "Updated"}

        response = await client.patch("/api/categories/nonexistent", json=updates)

        assert response.status_code == 404

    async def test_update_category_invalid_shelf_life(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/categories/{id} should reject invalid shelf life values."""
        updates = {"default_shelf_life_days": -5}

        response = await client.patch("/api/categories/meat", json=updates)

        assert response.status_code == 422  # Validation error


class TestDeleteCategory:
    """Test DELETE /api/categories/{id} endpoint."""

    async def test_delete_category_success(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """DELETE /api/categories/{id} should delete category."""
        response = await client.delete("/api/categories/snacks")

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get("/api/categories/snacks")
        assert get_response.status_code == 404

    async def test_delete_category_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """DELETE /api/categories/{id} should return 404 for non-existent category."""
        response = await client.delete("/api/categories/nonexistent")

        assert response.status_code == 404

    async def test_delete_category_idempotent(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """DELETE /api/categories/{id} should be idempotent."""
        # Delete once
        response1 = await client.delete("/api/categories/snacks")
        assert response1.status_code == 204

        # Delete again
        response2 = await client.delete("/api/categories/snacks")
        assert response2.status_code == 404  # Already deleted


class TestDeleteCategoryThatIsInUse:
    """A category with products must answer 409, never 500 (H05, F1 Critical #2)."""

    async def test_a_category_with_products_answers_409(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Rye Bread",
                "category": "bread",
                "storage_type": "pantry",
                "default_shelf_life_days": 5,
                "unit_type": "count",
                "default_unit": "pcs",
            },
        )
        assert response.status_code == 201

        refused = await client.delete("/api/categories/bread")

        assert refused.status_code == 409
        assert "1 product" in refused.json()["detail"]

    async def test_the_category_survives_the_refusal(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        await client.post(
            "/api/products",
            json={
                "canonical_name": "Rye Bread",
                "category": "bread",
                "storage_type": "pantry",
                "default_shelf_life_days": 5,
                "unit_type": "count",
                "default_unit": "pcs",
            },
        )

        await client.delete("/api/categories/bread")

        still_there = await client.get("/api/categories/bread")
        assert still_there.status_code == 200

    async def test_an_empty_category_still_deletes(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        assert (await client.delete("/api/categories/snacks")).status_code == 204
