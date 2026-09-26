"""Tests for Product CRUD API endpoints."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.store_product_alias import StoreProductAlias


async def _placeholder(db: AsyncSession, fields: dict) -> dict:
    """A product whose shelf life is still its category's placeholder.

    `POST /products` used to store exactly this, mislabelled; since Q19 a shelf life typed
    there is the cook's. A placeholder is what quick add and receipt confirm create, so
    it is made the way they make it: stored with `shelf_life_source = "category"`.
    """
    product = ProductMaster(**fields, shelf_life_source="category")
    db.add(product)
    await db.commit()
    return {"id": str(product.id), "shelf_life_source": str(product.shelf_life_source)}


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
            "default_unit": "dl",
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
                "default_unit": "dl",
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
            "default_unit": "dl",
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
            "default_unit": "dl",
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
        # DEC-2: Decimal fields travel as JSON numbers, not strings
        assert product["default_quantity"] == 1000
        assert product["min_stock_quantity"] == 2000
        assert product["reorder_quantity"] == 4000
        assert isinstance(product["default_quantity"], int | float)

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
            "default_unit": "dl",
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
            "default_unit": "dl",
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
            "default_unit": "dl",
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


class TestProductCanonicalUnits:
    """MVP-U1: product default quantities convert to canonical units; unit_type follows."""

    async def test_kilograms_become_grams_and_weight(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Emmental 1kg",
                "category": "cheese",
                "storage_type": "refrigerator",
                "default_shelf_life_days": 25,
                "unit_type": "count",
                "default_unit": "kg",
                "default_quantity": 1,
                "min_stock_quantity": 0.25,
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert (body["default_unit"], body["unit_type"]) == ("g", "weight")
        assert (body["default_quantity"], body["min_stock_quantity"]) == (1000, 250)

    async def test_millilitres_become_decilitres_and_volume(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Oat drink 1L",
                "category": "beverages",
                "storage_type": "pantry",
                "default_shelf_life_days": 90,
                "unit_type": "volume",
                "default_unit": "ml",
                "default_quantity": 1000,
            },
        )
        body = response.json()
        assert (body["default_unit"], body["unit_type"], body["default_quantity"]) == (
            "dl",
            "volume",
            10,
        )

    async def test_update_with_unit_converts_amounts(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        created = await client.post(
            "/api/products",
            json={
                "canonical_name": "Rice",
                "category": "pantry",
                "storage_type": "pantry",
                "default_shelf_life_days": 365,
                "unit_type": "weight",
                "default_unit": "g",
                "default_quantity": 500,
            },
        )
        product_id = created.json()["id"]

        updated = await client.patch(
            f"/api/products/{product_id}",
            json={"default_unit": "kg", "default_quantity": 2},
        )

        body = updated.json()
        assert (body["default_unit"], body["default_quantity"], body["unit_type"]) == (
            "g",
            2000,
            "weight",
        )

    async def test_unknown_unit_is_rejected(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Imported syrup",
                "category": "condiments",
                "storage_type": "pantry",
                "default_shelf_life_days": 365,
                "unit_type": "volume",
                "default_unit": "floz",
            },
        )
        assert response.status_code == 422


class TestPieceWeightThroughTheAPI:
    """Q2 stored a piece weight but never exposed it; a correction needs both directions."""

    PRODUCT = {
        "canonical_name": "Apple",
        "category": "fruits",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 21,
        "unit_type": "count",
        "default_unit": "pcs",
    }

    async def test_it_round_trips_through_create_and_read(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        created = await client.post(
            "/api/products", json={**self.PRODUCT, "avg_piece_grams": 125}
        )

        assert created.status_code == 201
        assert created.json()["avg_piece_grams"] == 125

        fetched = await client.get(f"/api/products/{created.json()['id']}")
        assert fetched.json()["avg_piece_grams"] == 125

    async def test_a_bad_estimate_can_be_corrected(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (
            await client.post(
                "/api/products", json={**self.PRODUCT, "avg_piece_grams": 125}
            )
        ).json()

        response = await client.patch(
            f"/api/products/{product['id']}", json={"avg_piece_grams": 180}
        )

        assert response.status_code == 200
        assert response.json()["avg_piece_grams"] == 180

    async def test_a_product_without_one_reads_as_null(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        created = await client.post("/api/products", json=self.PRODUCT)

        assert created.json()["avg_piece_grams"] is None

    async def test_a_weightless_piece_is_rejected(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Zero would divide a real purchase into nothing."""
        response = await client.post(
            "/api/products", json={**self.PRODUCT, "avg_piece_grams": 0}
        )

        assert response.status_code == 422


class TestDeleteProductThatIsInUse:
    """A referenced product must answer 409, never 500 (H05, F1 Critical #1).

    Confirming a receipt writes a store_product_alias row for every product
    (receipt_confirm.py), so in practice almost every real product has one.
    """

    async def _product(self, client: AsyncClient) -> dict:
        response = await client.post(
            "/api/products",
            json={
                "canonical_name": "Referenced Milk",
                "category": "dairy",
                "storage_type": "refrigerator",
                "default_shelf_life_days": 7,
                "unit_type": "volume",
                "default_unit": "dl",
            },
        )
        assert response.status_code == 201
        return response.json()

    async def test_referenced_by_inventory_answers_409(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        seeded_db.add(
            InventoryItem(
                id=uuid4(),
                product_master_id=UUID(product["id"]),
                initial_quantity=Decimal("1000"),
                current_quantity=Decimal("1000"),
                unit="dl",
                status="sealed",
                expiry_date=date.today() + timedelta(days=7),
            )
        )
        await seeded_db.commit()

        response = await client.delete(f"/api/products/{product['id']}")

        assert response.status_code == 409
        assert "inventory item" in response.json()["detail"]

    async def test_referenced_by_a_receipt_alias_answers_409(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        seeded_db.add(
            StoreProductAlias(
                id=uuid4(),
                product_master_id=UUID(product["id"]),
                store_chain="s-market",
                receipt_name="VALIO MAITO 1L",
            )
        )
        await seeded_db.commit()

        response = await client.delete(f"/api/products/{product['id']}")

        assert response.status_code == 409
        detail = response.json()["detail"]
        assert "alias" in detail

    async def test_the_conflict_counts_every_kind_of_reference(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        for _ in range(2):
            seeded_db.add(
                InventoryItem(
                    id=uuid4(),
                    product_master_id=UUID(product["id"]),
                    initial_quantity=Decimal("1000"),
                    current_quantity=Decimal("1000"),
                    unit="dl",
                    status="sealed",
                    expiry_date=date.today() + timedelta(days=7),
                )
            )
        seeded_db.add(
            StoreProductAlias(
                id=uuid4(),
                product_master_id=UUID(product["id"]),
                store_chain="s-market",
                receipt_name="VALIO MAITO 1L",
            )
        )
        await seeded_db.commit()

        response = await client.delete(f"/api/products/{product['id']}")

        detail = response.json()["detail"]
        assert "2 inventory items" in detail
        assert "1 receipt name alias" in detail

    async def test_the_product_survives_the_refusal(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        seeded_db.add(
            StoreProductAlias(
                id=uuid4(),
                product_master_id=UUID(product["id"]),
                store_chain="s-market",
                receipt_name="VALIO MAITO 1L",
            )
        )
        await seeded_db.commit()

        await client.delete(f"/api/products/{product['id']}")

        still_there = await client.get(f"/api/products/{product['id']}")
        assert still_there.status_code == 200

    async def test_no_error_body_carries_raw_database_text(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """`detail` is rendered to the cook verbatim by the frontend API client,
        so it must not carry asyncpg's DETAIL line, which quotes row values."""
        product = await self._product(client)
        seeded_db.add(
            StoreProductAlias(
                id=uuid4(),
                product_master_id=UUID(product["id"]),
                store_chain="s-market",
                receipt_name="VALIO MAITO 1L",
            )
        )
        await seeded_db.commit()

        refused = await client.delete(f"/api/products/{product['id']}")
        bad_category = await client.post(
            "/api/products",
            json={
                "canonical_name": "Orphan",
                "category": "nonexistent_category",
                "storage_type": "pantry",
                "default_shelf_life_days": 365,
                "unit_type": "count",
                "default_unit": "pcs",
            },
        )

        for response in (refused, bad_category):
            detail = response.json()["detail"]
            assert "Key (" not in detail
            assert "is still referenced" not in detail
            assert "DETAIL" not in detail


class TestShelfLifeProvenanceThroughTheAPI:
    """Q11: the editor is how a cook overrules the catalog, and it has to be recorded.

    `update_product` sets fields with a blind `setattr` loop, so before this the PATCH
    that fixes mince had no idea it was the cook speaking - and the next receipt would
    have been free to overwrite the correction.
    """

    PRODUCT = {
        "canonical_name": "Ground beef",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 5,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def test_a_shelf_life_the_cook_typed_is_marked_as_theirs(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        response = await client.patch(
            f"/api/products/{product['id']}", json={"default_shelf_life_days": 2}
        )

        assert response.status_code == 200
        assert response.json()["default_shelf_life_days"] == 2
        assert response.json()["shelf_life_source"] == "cook"

    async def test_editing_something_else_leaves_the_provenance_alone(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _placeholder(seeded_db, self.PRODUCT)

        response = await client.patch(
            f"/api/products/{product['id']}", json={"avg_piece_grams": 125}
        )

        assert response.json()["shelf_life_source"] == "category"

    async def test_the_caller_cannot_claim_a_provenance(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Provenance is derived from what the writer did, never asserted in the payload.

        Creating a product here means typing its shelf life, so it is the cook's (Q19).
        """
        product = (
            await client.post(
                "/api/products", json={**self.PRODUCT, "shelf_life_source": "category"}
            )
        ).json()

        assert product["shelf_life_source"] == "cook"

    async def test_it_is_readable_on_every_product(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """The products screen needs it to say which figures are guesses."""
        await client.post("/api/products", json=self.PRODUCT)

        listed = (await client.get("/api/products")).json()

        assert listed
        assert all("shelf_life_source" in product for product in listed)


class TestEstimateCatalogEndpoint:
    """Q11: POST /api/products/estimate, and why it does not write by default."""

    PRODUCT = {
        "canonical_name": "Ground beef",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 5,
        "unit_type": "weight",
        "default_unit": "g",
    }

    def _says(self, product_id: str, days: int):
        from app.services.catalog_estimates import Estimate

        return patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            return_value=[
                Estimate(
                    id=product_id, shelf_life_days=days, opened_shelf_life_days=None
                )
            ],
        )

    async def test_a_dry_run_is_the_default_and_writes_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _placeholder(seeded_db, self.PRODUCT)

        with self._says(product["id"], 2):
            response = await client.post("/api/products/estimate")

        assert response.status_code == 200
        body = response.json()
        assert body["applied"] is False
        assert body["considered"] == 1
        assert body["changes"][0]["current_days"] == 5
        assert body["changes"][0]["proposed_days"] == 2

        unchanged = (await client.get(f"/api/products/{product['id']}")).json()
        assert unchanged["default_shelf_life_days"] == 5

    async def test_applying_writes_and_says_so(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _placeholder(seeded_db, self.PRODUCT)

        with self._says(product["id"], 2):
            response = await client.post("/api/products/estimate?apply=true")

        assert response.json()["applied"] is True

        updated = (await client.get(f"/api/products/{product['id']}")).json()
        assert updated["default_shelf_life_days"] == 2
        assert updated["shelf_life_source"] == "model"

    async def test_a_gateway_that_cannot_answer_is_a_503_not_a_500(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """H05's rule: no 500 on a reachable route. Nothing is written either."""
        from app.services.llm_extractor import LLMExtractionError

        product = await _placeholder(seeded_db, self.PRODUCT)

        with patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            side_effect=LLMExtractionError("gateway is down"),
        ):
            response = await client.post("/api/products/estimate?apply=true")

        assert response.status_code == 503
        untouched = (await client.get(f"/api/products/{product['id']}")).json()
        assert untouched["default_shelf_life_days"] == 5

    async def test_a_catalog_with_nothing_to_fix_asks_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        await client.patch(
            f"/api/products/{product['id']}", json={"default_shelf_life_days": 2}
        )

        response = await client.post("/api/products/estimate")

        assert response.json()["considered"] == 0


class TestEstimateScope:
    """Q19: `scope=all` re-estimates every product the cook has not set.

    For after the estimator's prompt was recalibrated: the model's earlier answers were
    made against the old examples, and they are the system's own work, not the cook's.
    """

    PRODUCT = {
        "canonical_name": "Tomato",
        "category": "produce",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 7,
        "unit_type": "count",
        "default_unit": "pcs",
    }

    async def _catalog(self, db: AsyncSession) -> dict[str, str]:
        placeholder = await _placeholder(db, self.PRODUCT)
        guessed = ProductMaster(
            **{**self.PRODUCT, "canonical_name": "Orange"}, shelf_life_source="model"
        )
        cooks = ProductMaster(
            **{**self.PRODUCT, "canonical_name": "Banana"}, shelf_life_source="cook"
        )
        db.add_all([guessed, cooks])
        await db.commit()
        return {
            "Tomato": placeholder["id"],
            "Orange": str(guessed.id),
            "Banana": str(cooks.id),
        }

    def _asking(self, asked: list[str], days: int = 21):
        from app.services.catalog_estimates import Estimate

        async def answer(products):
            asked.extend(p.name for p in products)
            return [
                Estimate(id=p.id, shelf_life_days=days, opened_shelf_life_days=None)
                for p in products
            ]

        return patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new=AsyncMock(side_effect=answer),
        )

    async def test_guesses_is_the_default(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        await self._catalog(seeded_db)
        asked: list[str] = []

        with self._asking(asked):
            response = await client.post("/api/products/estimate")

        assert response.status_code == 200
        assert asked == ["Tomato"]

    async def test_all_is_a_dry_run_over_everything_but_the_cooks(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        ids = await self._catalog(seeded_db)
        asked: list[str] = []

        with self._asking(asked):
            response = await client.post("/api/products/estimate?scope=all")

        assert response.status_code == 200
        body = response.json()
        assert sorted(asked) == ["Orange", "Tomato"]  # the cook's Banana is never sent
        assert body["applied"] is False
        assert body["considered"] == 2
        assert sorted(c["canonical_name"] for c in body["changes"]) == [
            "Orange",
            "Tomato",
        ]
        orange = (await client.get(f"/api/products/{ids['Orange']}")).json()
        assert orange["default_shelf_life_days"] == 7

    async def test_all_applied_keeps_the_cooks_number(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        ids = await self._catalog(seeded_db)

        with self._asking([]):
            response = await client.post("/api/products/estimate?scope=all&apply=true")

        assert response.json()["applied"] is True
        for name in ("Tomato", "Orange"):
            updated = (await client.get(f"/api/products/{ids[name]}")).json()
            assert (
                updated["default_shelf_life_days"],
                updated["shelf_life_source"],
            ) == (21, "model")
        banana = (await client.get(f"/api/products/{ids['Banana']}")).json()
        assert (banana["default_shelf_life_days"], banana["shelf_life_source"]) == (
            7,
            "cook",
        )

    async def test_an_unknown_scope_is_a_422(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.post("/api/products/estimate?scope=everything")

        assert response.status_code == 422


class TestCorrectionReachesTheFood:
    """Q12: the sequence HANDOFF.md recommends, end to end.

    Before this, confirming a receipt and then correcting the shelf life - by hand or
    through the catalog estimate - left the stock dated by the number that had just been
    replaced, with nothing on screen saying so.
    """

    PRODUCT = {
        "canonical_name": "Ground beef",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 5,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def _stock(self, client: AsyncClient, product_id: str) -> dict:
        response = await client.post(
            "/api/inventory",
            json={
                "product_master_id": product_id,
                "initial_quantity": 400,
                "current_quantity": 400,
                "unit": "g",
                "purchase_date": "2026-09-01",
                "expiry_date": "2026-09-06",
                "expiry_source": "calculated",
                "location": "main_fridge",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def test_correcting_by_hand_moves_the_stock(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])

        await client.patch(
            f"/api/products/{product['id']}", json={"default_shelf_life_days": 2}
        )

        moved = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert moved["expiry_date"] == "2026-09-03"

    async def test_a_date_you_typed_is_left_where_you_put_it(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])
        await client.patch(
            f"/api/inventory/{item['id']}", json={"expiry_date": "2026-12-24"}
        )

        await client.patch(
            f"/api/products/{product['id']}", json={"default_shelf_life_days": 2}
        )

        untouched = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert untouched["expiry_date"] == "2026-12-24"
        assert untouched["expiry_source"] == "manual"

    async def test_editing_something_else_moves_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])

        await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Minced beef"}
        )

        same = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert same["expiry_date"] == "2026-09-06"

    async def test_the_catalog_estimate_moves_the_stock_too(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """The whole point: this is the button HANDOFF.md tells the cook to press."""
        from app.services.catalog_estimates import Estimate

        product = await _placeholder(seeded_db, self.PRODUCT)
        item = await self._stock(client, product["id"])

        with patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            return_value=[
                Estimate(
                    id=product["id"], shelf_life_days=2, opened_shelf_life_days=None
                )
            ],
        ):
            response = await client.post("/api/products/estimate?apply=true")

        assert response.json()["items_redated"] == 1

        moved = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert moved["expiry_date"] == "2026-09-03"

    async def test_a_dry_run_moves_no_stock(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        from app.services.catalog_estimates import Estimate

        product = await _placeholder(seeded_db, self.PRODUCT)
        item = await self._stock(client, product["id"])

        with patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            return_value=[
                Estimate(
                    id=product["id"], shelf_life_days=2, opened_shelf_life_days=None
                )
            ],
        ):
            response = await client.post("/api/products/estimate")

        assert response.json()["items_redated"] == 0

        unchanged = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert unchanged["expiry_date"] == "2026-09-06"


class TestProductFrozenLife:
    """H52: frozen life lives on the product, and falls back to the category."""

    PRODUCT = {
        "canonical_name": "Bacon",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 5,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def test_a_new_product_has_none_of_its_own(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        assert product["frozen_shelf_life_days"] is None

    async def test_the_cook_can_set_it_and_take_it_back(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        set_ = await client.patch(
            f"/api/products/{product['id']}", json={"frozen_shelf_life_days": 30}
        )
        cleared = await client.patch(
            f"/api/products/{product['id']}", json={"frozen_shelf_life_days": None}
        )

        assert set_.json()["frozen_shelf_life_days"] == 30
        assert cleared.json()["frozen_shelf_life_days"] is None

    async def test_zero_days_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        response = await client.patch(
            f"/api/products/{product['id']}", json={"frozen_shelf_life_days": 0}
        )

        assert response.status_code == 422


class TestCategoryChange:
    """H52: a product filed under the wrong category can be moved, and a placeholder
    shelf life moves with it - it only ever meant "what the category says"."""

    PRODUCT = {
        "canonical_name": "Salmon fillet",
        "category": "meat",
        "storage_type": "refrigerator",
        "default_shelf_life_days": 5,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def _stock(self, client: AsyncClient, product_id: str) -> dict:
        response = await client.post(
            "/api/inventory",
            json={
                "product_master_id": product_id,
                "initial_quantity": 400,
                "current_quantity": 400,
                "unit": "g",
                "purchase_date": "2026-09-01",
                "expiry_date": "2026-09-06",
                "expiry_source": "calculated",
                "location": "main_fridge",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def test_a_placeholder_follows_the_new_category(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _placeholder(seeded_db, self.PRODUCT)
        assert product["shelf_life_source"] == "category"

        moved = (
            await client.patch(
                f"/api/products/{product['id']}", json={"category": "fish"}
            )
        ).json()

        assert moved["category"] == "fish"
        assert moved["default_shelf_life_days"] == 3
        assert moved["shelf_life_source"] == "category"

    async def test_the_stock_it_dated_moves_too(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await _placeholder(seeded_db, self.PRODUCT)
        item = await self._stock(client, product["id"])

        await client.patch(f"/api/products/{product['id']}", json={"category": "fish"})

        after = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert after["expiry_date"] == "2026-09-04"

    async def test_a_shelf_life_the_cook_typed_stays(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        await client.patch(
            f"/api/products/{product['id']}", json={"default_shelf_life_days": 10}
        )

        moved = (
            await client.patch(
                f"/api/products/{product['id']}", json={"category": "fish"}
            )
        ).json()

        assert moved["default_shelf_life_days"] == 10
        assert moved["shelf_life_source"] == "cook"

    async def test_a_shelf_life_sent_with_the_category_wins(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        moved = (
            await client.patch(
                f"/api/products/{product['id']}",
                json={"category": "fish", "default_shelf_life_days": 2},
            )
        ).json()

        assert moved["default_shelf_life_days"] == 2
        assert moved["shelf_life_source"] == "cook"

    async def test_storage_follows_the_category(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """For stock added later; what is in the kitchen already stays where it is."""
        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        item = await self._stock(client, product["id"])

        moved = (
            await client.patch(
                f"/api/products/{product['id']}", json={"category": "pantry"}
            )
        ).json()

        assert moved["storage_type"] == "pantry"
        after = (await client.get(f"/api/inventory/{item['id']}")).json()
        assert after["location"] == "main_fridge"

    async def test_an_unknown_category_is_refused(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        response = await client.patch(
            f"/api/products/{product['id']}", json={"category": "nonsense"}
        )

        assert response.status_code in (400, 409)


class TestRenameKeepsNames:
    """H52: a rename used to leave `product_name` behind - the old canonical row stayed
    canonical (and so unremovable) and the new name had no row at all."""

    PRODUCT = {
        "canonical_name": "Taco sauce",
        "category": "condiments",
        "storage_type": "pantry",
        "default_shelf_life_days": 180,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def _names(self, client: AsyncClient, product_id: str) -> dict[str, str]:
        response = await client.get(f"/api/products/{product_id}/names")
        assert response.status_code == 200, response.text
        return {row["name"]: row["source"] for row in response.json()["names"]}

    async def test_the_new_name_is_canonical_and_the_old_one_the_cooks(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Salsa"}
        )

        assert await self._names(client, product["id"]) == {
            "salsa": "canonical",
            "taco sauce": "cook",
        }

    async def test_both_names_still_find_it(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        from app.services.product_names import known_names

        product = (await client.post("/api/products", json=self.PRODUCT)).json()
        await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Salsa"}
        )

        found = await known_names(seeded_db, ["Salsa", "Taco sauce"])

        assert {str(k.product.id) for k in found.values()} == {product["id"]}

    async def test_a_name_another_product_owns_stays_theirs(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """First claim wins; the canonical-name fallback still finds the renamed one."""
        from app.models.product_name import ProductName
        from app.services.product_names import product_for_name

        other = (
            await client.post(
                "/api/products", json={**self.PRODUCT, "canonical_name": "Ketchup"}
            )
        ).json()
        seeded_db.add(
            ProductName(
                product_master_id=UUID(other["id"]), name="salsa", source="cook"
            )
        )
        await seeded_db.commit()
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        response = await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Salsa"}
        )

        assert response.status_code == 200
        assert "salsa" not in await self._names(client, product["id"])
        assert str((await product_for_name(seeded_db, "Salsa")).id) == other["id"]

    async def test_renaming_back_makes_the_old_name_canonical_again(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Salsa"}
        )
        await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Taco sauce"}
        )

        assert await self._names(client, product["id"]) == {
            "taco sauce": "canonical",
            "salsa": "cook",
        }

    async def test_renaming_to_the_same_name_changes_nothing(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        await client.patch(
            f"/api/products/{product['id']}", json={"canonical_name": "Taco sauce"}
        )

        assert await self._names(client, product["id"]) == {"taco sauce": "canonical"}


class TestProductNames:
    """H52: the names a product answers to, and the cook's way to take one back.

    Q13 wrote "ketchup" as a key for Taco sauce; H51 stopped new ones being trusted, and
    this is the cleanup for the keys already written.
    """

    PRODUCT = {
        "canonical_name": "Taco sauce",
        "category": "condiments",
        "storage_type": "pantry",
        "default_shelf_life_days": 180,
        "unit_type": "weight",
        "default_unit": "g",
    }

    async def _product(self, client: AsyncClient, **overrides) -> dict:
        response = await client.post(
            "/api/products", json={**self.PRODUCT, **overrides}
        )
        assert response.status_code == 201, response.text
        return response.json()

    async def _learn(
        self, db: AsyncSession, product_id: str, name: str, source: str
    ) -> None:
        from app.models.product_name import ProductName

        db.add(
            ProductName(product_master_id=UUID(product_id), name=name, source=source)
        )
        await db.commit()

    async def _alias(
        self, db: AsyncSession, product_id: str, printed: str, **fields
    ) -> None:
        db.add(
            StoreProductAlias(
                id=uuid4(),
                product_master_id=UUID(product_id),
                store_chain="s-market",
                receipt_name=printed,
                **fields,
            )
        )
        await db.commit()

    async def test_lists_learned_and_printed_names_with_their_source(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        await self._learn(seeded_db, product["id"], "ketchup", "model")
        await self._learn(seeded_db, product["id"], "tacokastike", "cook")
        await self._alias(
            seeded_db,
            product["id"],
            "PIRKKA TACOKASTIKE",
            source="model",
            manually_verified=False,
        )

        response = await client.get(f"/api/products/{product['id']}/names")

        assert response.status_code == 200
        body = response.json()
        names = {row["name"]: row for row in body["names"]}
        assert names["taco sauce"]["source"] == "canonical"
        assert names["taco sauce"]["removable"] is False
        assert names["ketchup"]["source"] == "model"
        assert names["ketchup"]["removable"] is True
        assert names["tacokastike"]["source"] == "cook"
        [printed] = body["printed"]
        assert printed["receipt_name"] == "PIRKKA TACOKASTIKE"
        assert printed["store_chain"] == "s-market"
        assert printed["source"] == "model"
        assert printed["verified"] is False

    async def test_an_unknown_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        response = await client.get(f"/api/products/{uuid4()}/names")

        assert response.status_code == 404

    async def test_removing_a_learned_name_stops_it_resolving(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """The reported pair: "ketchup" must stop meaning Taco sauce."""
        from app.services.product_names import known_names

        product = await self._product(client)
        await self._learn(seeded_db, product["id"], "ketchup", "model")
        listed = (await client.get(f"/api/products/{product['id']}/names")).json()
        ketchup = next(row for row in listed["names"] if row["name"] == "ketchup")

        response = await client.delete(
            f"/api/products/{product['id']}/names/{ketchup['id']}"
        )

        assert response.status_code == 204
        assert await known_names(seeded_db, ["ketchup"]) == {}

    async def test_the_canonical_name_cannot_be_removed(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Rename the product instead; without it the product has no key at all."""
        product = await self._product(client)
        listed = (await client.get(f"/api/products/{product['id']}/names")).json()
        [canonical] = listed["names"]

        response = await client.delete(
            f"/api/products/{product['id']}/names/{canonical['id']}"
        )

        assert response.status_code == 409
        after = (await client.get(f"/api/products/{product['id']}/names")).json()
        assert [row["name"] for row in after["names"]] == ["taco sauce"]

    async def test_a_name_of_another_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        other = await self._product(client, canonical_name="Ketchup")
        await self._learn(seeded_db, other["id"], "tomato ketchup", "cook")
        listed = (await client.get(f"/api/products/{other['id']}/names")).json()
        theirs = next(row for row in listed["names"] if row["name"] == "tomato ketchup")

        response = await client.delete(
            f"/api/products/{product['id']}/names/{theirs['id']}"
        )

        assert response.status_code == 404

    async def test_removing_a_printed_name_forgets_the_alias(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        await self._alias(seeded_db, product["id"], "PIRKKA KETCHUP", source="model")
        listed = (await client.get(f"/api/products/{product['id']}/names")).json()
        [printed] = listed["printed"]

        response = await client.delete(
            f"/api/products/{product['id']}/aliases/{printed['id']}"
        )

        assert response.status_code == 204
        after = (await client.get(f"/api/products/{product['id']}/names")).json()
        assert after["printed"] == []

    async def test_a_printed_name_of_another_product_is_404(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        product = await self._product(client)
        other = await self._product(client, canonical_name="Ketchup")
        await self._alias(seeded_db, other["id"], "PIRKKA KETCHUP")
        listed = (await client.get(f"/api/products/{other['id']}/names")).json()
        [theirs] = listed["printed"]

        response = await client.delete(
            f"/api/products/{product['id']}/aliases/{theirs['id']}"
        )

        assert response.status_code == 404
