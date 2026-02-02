"""Tests for Product CRUD API endpoints."""
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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


class TestListProducts:
    """Test GET /api/products endpoint."""

    async def test_list_products_empty_list(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products should return empty list when no products exist."""
        response = await client.get("/api/products")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_list_products_returns_all_products(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products should return all products."""
        # Create test products
        product1 = {
            "canonical_name": "Valio Whole Milk 1L",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }
        product2 = {
            "canonical_name": "Chicken Breast",
            "category": "meat",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 5,
            "unit_type": "weight",
            "default_unit": "g",
        }

        await client.post("/api/products", json=product1)
        await client.post("/api/products", json=product2)

        response = await client.get("/api/products")

        assert response.status_code == 200
        products = response.json()
        assert len(products) == 2

    async def test_list_products_search_by_name(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products?search= should filter by name."""
        products_data = [
            {
                "canonical_name": "Valio Whole Milk 1L",
                "category": "dairy",
                "storage_type": "refrigerator",
                "default_shelf_life_days": 7,
                "unit_type": "volume",
                "default_unit": "ml",
            },
            {
                "canonical_name": "Chicken Breast",
                "category": "meat",
                "storage_type": "refrigerator",
                "default_shelf_life_days": 5,
                "unit_type": "weight",
                "default_unit": "g",
            },
        ]

        for product_data in products_data:
            await client.post("/api/products", json=product_data)

        response = await client.get("/api/products?search=milk")

        assert response.status_code == 200
        products = response.json()
        assert len(products) == 1
        assert "Milk" in products[0]["canonical_name"]


class TestGetProduct:
    """Test GET /api/products/{id} endpoint."""

    async def test_get_product_returns_product(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products/{id} should return specific product."""
        product_data = {
            "canonical_name": "Test Product",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }

        create_response = await client.post("/api/products", json=product_data)
        created_product = create_response.json()

        response = await client.get(f"/api/products/{created_product['id']}")

        assert response.status_code == 200
        product = response.json()
        assert product["canonical_name"] == "Test Product"
        assert product["category"] == "dairy"

    async def test_get_product_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products/{id} should return 404 for non-existent product."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/products/{fake_uuid}")

        assert response.status_code == 404
        assert "detail" in response.json()


class TestCreateProduct:
    """Test POST /api/products endpoint."""

    async def test_create_product_success(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products should create a new product."""
        new_product = {
            "canonical_name": "Valio Whole Milk 1L",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "opened_shelf_life_days": 3,
            "unit_type": "volume",
            "default_unit": "ml",
            "default_quantity": 1000,
            "min_stock_quantity": 2000,
            "reorder_quantity": 4000,
        }

        response = await client.post("/api/products", json=new_product)

        assert response.status_code == 201
        product = response.json()
        assert product["canonical_name"] == "Valio Whole Milk 1L"
        assert product["category"] == "dairy"
        assert "id" in product
        assert UUID(product["id"])  # Valid UUID

    async def test_create_product_minimal_fields(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products should work with only required fields."""
        minimal_product = {
            "canonical_name": "Minimal Product",
            "category": "pantry",
            "storage_type": "pantry",
            "default_shelf_life_days": 365,
            "unit_type": "count",
            "default_unit": "pcs",
        }

        response = await client.post("/api/products", json=minimal_product)

        assert response.status_code == 201

    async def test_create_product_invalid_category(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products should reject invalid category."""
        invalid_product = {
            "canonical_name": "Test Product",
            "category": "nonexistent_category",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }

        response = await client.post("/api/products", json=invalid_product)

        assert response.status_code == 400

    async def test_create_product_missing_required_fields(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products should reject requests with missing required fields."""
        incomplete_product = {
            "canonical_name": "Incomplete Product",
            # Missing category, storage_type, etc.
        }

        response = await client.post("/api/products", json=incomplete_product)

        assert response.status_code == 422  # Validation error


class TestUpdateProduct:
    """Test PATCH /api/products/{id} endpoint."""

    async def test_update_product_success(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/products/{id} should update product fields."""
        # Create a product first
        product_data = {
            "canonical_name": "Original Name",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
        }

        create_response = await client.post("/api/products", json=product_data)
        created_product = create_response.json()

        # Update it
        updates = {
            "canonical_name": "Updated Name",
            "default_shelf_life_days": 10,
        }

        response = await client.patch(
            f"/api/products/{created_product['id']}", json=updates
        )

        assert response.status_code == 200
        product = response.json()
        assert product["canonical_name"] == "Updated Name"
        assert product["default_shelf_life_days"] == 10
        assert product["category"] == "dairy"  # Unchanged

    async def test_update_product_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """PATCH /api/products/{id} should return 404 for non-existent product."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        updates = {"canonical_name": "Updated"}

        response = await client.patch(f"/api/products/{fake_uuid}", json=updates)

        assert response.status_code == 404


class TestDeleteProduct:
    """Test DELETE /api/products/{id} endpoint."""

    async def test_delete_product_success(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """DELETE /api/products/{id} should delete product."""
        # Create a product first
        product_data = {
            "canonical_name": "To Delete",
            "category": "pantry",
            "storage_type": "pantry",
            "default_shelf_life_days": 365,
            "unit_type": "count",
            "default_unit": "pcs",
        }

        create_response = await client.post("/api/products", json=product_data)
        created_product = create_response.json()

        # Delete it
        response = await client.delete(f"/api/products/{created_product['id']}")

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get(f"/api/products/{created_product['id']}")
        assert get_response.status_code == 404

    async def test_delete_product_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """DELETE /api/products/{id} should return 404 for non-existent product."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"/api/products/{fake_uuid}")

        assert response.status_code == 404


class TestLookupByBarcode:
    """Test GET /api/products/barcode/{barcode} endpoint."""

    async def test_lookup_barcode_returns_product(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products/barcode/{barcode} should return product with matching barcode."""
        product_data = {
            "canonical_name": "Product with Barcode",
            "category": "dairy",
            "storage_type": "refrigerator",
            "default_shelf_life_days": 7,
            "unit_type": "volume",
            "default_unit": "ml",
            "off_product_id": "1234567890123",
        }

        await client.post("/api/products", json=product_data)

        response = await client.get("/api/products/barcode/1234567890123")

        assert response.status_code == 200
        product = response.json()
        assert product["canonical_name"] == "Product with Barcode"
        assert product["off_product_id"] == "1234567890123"

    async def test_lookup_barcode_not_found(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """GET /api/products/barcode/{barcode} should return 404 for unknown barcode."""
        response = await client.get("/api/products/barcode/9999999999999")

        assert response.status_code == 404


class TestEnrichProduct:
    """Test POST /api/products/enrich endpoint."""

    async def test_enrich_creates_new_product_from_off(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products/enrich should create new product from OFF data."""
        from unittest.mock import patch

        barcode = "5901234123457"
        mock_enriched_data = {
            "canonical_name": "Valio Whole Milk 1L",
            "category": "dairy",
            "off_product_id": barcode,
            "off_data": {
                "product_name": "Valio Whole Milk",
                "brands": "Valio",
                "categories": "Dairy products",
                "image_url": "https://example.com/milk.jpg",
            },
        }

        with patch(
            "app.api.endpoints.products.enrich_product_from_off",
            return_value=mock_enriched_data,
        ):
            response = await client.post(f"/api/products/enrich?barcode={barcode}")

            assert response.status_code == 201
            product = response.json()
            assert product["canonical_name"] == "Valio Whole Milk 1L"
            assert product["category"] == "dairy"
            assert product["off_product_id"] == barcode
            assert product["off_data"] is not None
            assert product["off_data"]["product_name"] == "Valio Whole Milk"

    async def test_enrich_updates_existing_product(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products/enrich should update existing product with same barcode."""
        from unittest.mock import patch

        barcode = "5901234123457"

        # Create existing product with this barcode
        existing_product = {
            "canonical_name": "Old Name",
            "category": "pantry",
            "storage_type": "pantry",
            "default_shelf_life_days": 365,
            "unit_type": "count",
            "default_unit": "pcs",
            "off_product_id": barcode,
        }
        create_response = await client.post("/api/products", json=existing_product)
        created = create_response.json()

        mock_enriched_data = {
            "canonical_name": "Valio Whole Milk 1L",
            "category": "dairy",
            "off_product_id": barcode,
            "off_data": {
                "product_name": "Valio Whole Milk",
                "brands": "Valio",
            },
        }

        with patch(
            "app.api.endpoints.products.enrich_product_from_off",
            return_value=mock_enriched_data,
        ):
            response = await client.post(f"/api/products/enrich?barcode={barcode}")

            assert response.status_code == 200
            product = response.json()
            assert product["id"] == created["id"]  # Same product
            assert product["canonical_name"] == "Valio Whole Milk 1L"  # Updated
            assert product["category"] == "dairy"  # Updated
            assert product["off_data"] is not None

    async def test_enrich_returns_404_when_not_found_in_off(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products/enrich should return 404 when product not in OFF."""
        from unittest.mock import patch
        from app.services.off_service import OffProductNotFoundError

        barcode = "0000000000000"

        with patch(
            "app.api.endpoints.products.enrich_product_from_off",
            side_effect=OffProductNotFoundError(barcode),
        ):
            response = await client.post(f"/api/products/enrich?barcode={barcode}")

            assert response.status_code == 404
            assert "not found in Open Food Facts" in response.json()["detail"]

    async def test_enrich_returns_503_on_api_error(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products/enrich should return 503 when OFF API fails."""
        from unittest.mock import patch
        from app.services.off_service import OffApiError

        barcode = "5901234123457"

        with patch(
            "app.api.endpoints.products.enrich_product_from_off",
            side_effect=OffApiError("Network error"),
        ):
            response = await client.post(f"/api/products/enrich?barcode={barcode}")

            assert response.status_code == 503
            assert "Open Food Facts API unavailable" in response.json()["detail"]

    async def test_enrich_requires_barcode_parameter(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """POST /api/products/enrich should require barcode parameter."""
        response = await client.post("/api/products/enrich")

        assert response.status_code == 422  # Validation error
