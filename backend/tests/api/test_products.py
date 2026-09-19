"""Tests for Product CRUD API endpoints."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.store_product_alias import StoreProductAlias


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
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

        response = await client.patch(
            f"/api/products/{product['id']}", json={"avg_piece_grams": 125}
        )

        assert response.json()["shelf_life_source"] == "category"

    async def test_the_caller_cannot_claim_to_be_the_cook(
        self, client: AsyncClient, seeded_db: AsyncSession
    ) -> None:
        """Provenance is derived from what the writer did, never asserted in the payload."""
        product = (
            await client.post(
                "/api/products", json={**self.PRODUCT, "shelf_life_source": "cook"}
            )
        ).json()

        assert product["shelf_life_source"] == "category"

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
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

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
        product = (await client.post("/api/products", json=self.PRODUCT)).json()

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

        product = (await client.post("/api/products", json=self.PRODUCT)).json()

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

        product = (await client.post("/api/products", json=self.PRODUCT)).json()
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

        product = (await client.post("/api/products", json=self.PRODUCT)).json()
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
