"""Tests for Open Food Facts service."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.off_service import (
    fetch_product_from_off,
    enrich_product_from_off,
    map_off_category_to_system,
    OffProductNotFoundError,
    OffApiError,
)


class TestFetchProductFromOff:
    """Tests for fetch_product_from_off function."""

    async def test_fetches_product_successfully(self):
        """Should fetch product data from OFF API successfully."""
        barcode = "5901234123457"
        mock_response_data = {
            "code": barcode,
            "status": 1,
            "product": {
                "product_name": "Test Milk",
                "brands": "Test Brand",
                "categories": "Dairy products, Milk",
                "image_url": "https://example.com/image.jpg",
                "nutriments": {
                    "energy-kcal_100g": 42,
                    "proteins_100g": 3.4,
                    "fat_100g": 1.5,
                },
                "quantity": "1L",
                "nutriscore_grade": "a",
            },
        }

        from unittest.mock import Mock

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        mock_response.raise_for_status = Mock()

        with patch("app.services.off_service.httpx.AsyncClient.get", return_value=mock_response):
            result = await fetch_product_from_off(barcode)

            assert result["code"] == barcode
            assert result["status"] == 1
            assert result["product"]["product_name"] == "Test Milk"
            assert result["product"]["brands"] == "Test Brand"

    async def test_raises_not_found_error_when_product_not_in_off(self):
        """Should raise OffProductNotFoundError when product not found."""
        from unittest.mock import Mock

        barcode = "0000000000000"
        mock_response_data = {"code": barcode, "status": 0}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)

        with patch("app.services.off_service.httpx.AsyncClient.get", return_value=mock_response):
            with pytest.raises(OffProductNotFoundError, match=f"Product {barcode} not found"):
                await fetch_product_from_off(barcode)

    async def test_raises_api_error_on_network_failure(self):
        """Should raise OffApiError on network failures."""
        barcode = "5901234123457"

        with patch(
            "app.services.off_service.httpx.AsyncClient.get",
            side_effect=Exception("Network error"),
        ):
            with pytest.raises(OffApiError, match="Failed to fetch product"):
                await fetch_product_from_off(barcode)

    async def test_raises_api_error_on_http_error(self):
        """Should raise OffApiError on HTTP errors."""
        import httpx
        from unittest.mock import Mock

        barcode = "5901234123457"

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=Mock(), response=mock_response
            )
        )

        with patch("app.services.off_service.httpx.AsyncClient.get", return_value=mock_response):
            with pytest.raises(OffApiError, match="Failed to fetch product"):
                await fetch_product_from_off(barcode)

    async def test_uses_correct_api_endpoint(self):
        """Should call the correct OFF API endpoint."""
        from unittest.mock import Mock

        barcode = "5901234123457"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"code": barcode, "status": 1, "product": {}})
        mock_response.raise_for_status = Mock()

        with patch("app.services.off_service.httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            await fetch_product_from_off(barcode)

            # Verify the API was called with correct URL
            expected_url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}"
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert expected_url in str(call_args)


class TestMapOffCategoryToSystem:
    """Tests for map_off_category_to_system function."""

    def test_maps_dairy_categories(self):
        """Should map dairy-related OFF categories to 'dairy'."""
        assert map_off_category_to_system("Dairy products") == "dairy"
        assert map_off_category_to_system("Milk and yogurt") == "dairy"
        assert map_off_category_to_system("Cheese") == "dairy"
        assert map_off_category_to_system("Yogurt") == "dairy"

    def test_maps_meat_categories(self):
        """Should map meat-related OFF categories to 'meat'."""
        assert map_off_category_to_system("Meats") == "meat"
        assert map_off_category_to_system("Chicken breast") == "meat"
        assert map_off_category_to_system("Fresh meat") == "meat"

    def test_maps_produce_categories(self):
        """Should map produce-related OFF categories to 'produce'."""
        assert map_off_category_to_system("Fruits") == "produce"
        assert map_off_category_to_system("Vegetables") == "produce"
        assert map_off_category_to_system("Fresh vegetables") == "produce"

    def test_maps_frozen_categories(self):
        """Should map frozen-related OFF categories to 'frozen'."""
        assert map_off_category_to_system("Frozen foods") == "frozen"
        assert map_off_category_to_system("Frozen vegetables") == "frozen"

    def test_maps_beverages_categories(self):
        """Should map beverage-related OFF categories to 'beverages'."""
        assert map_off_category_to_system("Beverages") == "beverages"
        assert map_off_category_to_system("Soft drinks") == "beverages"
        assert map_off_category_to_system("Juices") == "beverages"

    def test_returns_pantry_for_unknown_categories(self):
        """Should default to 'pantry' for unknown categories."""
        assert map_off_category_to_system("Unknown category") == "pantry"
        assert map_off_category_to_system("") == "pantry"
        assert map_off_category_to_system(None) == "pantry"


class TestEnrichProductFromOff:
    """Tests for enrich_product_from_off function."""

    async def test_enriches_product_with_full_data(self):
        """Should enrich product data from OFF successfully."""
        barcode = "5901234123457"
        mock_off_data = {
            "code": barcode,
            "status": 1,
            "product": {
                "product_name": "Valio Whole Milk",
                "brands": "Valio",
                "categories": "Dairy products, Milk",
                "image_url": "https://example.com/milk.jpg",
                "nutriments": {"energy-kcal_100g": 64, "proteins_100g": 3.4},
                "quantity": "1L",
                "nutriscore_grade": "a",
            },
        }

        with patch("app.services.off_service.fetch_product_from_off", return_value=mock_off_data):
            result = await enrich_product_from_off(barcode)

            assert result["canonical_name"] == "Valio Whole Milk 1L"
            assert result["category"] == "dairy"
            assert result["off_product_id"] == barcode
            assert result["off_data"] == mock_off_data["product"]

    async def test_enriches_product_with_minimal_data(self):
        """Should handle products with minimal OFF data."""
        barcode = "0000000000000"
        mock_off_data = {
            "code": barcode,
            "status": 1,
            "product": {
                "product_name": "Unknown Product",
                # No brands, categories, etc.
            },
        }

        with patch("app.services.off_service.fetch_product_from_off", return_value=mock_off_data):
            result = await enrich_product_from_off(barcode)

            assert result["canonical_name"] == "Unknown Product"
            assert result["category"] == "pantry"  # Default category
            assert result["off_product_id"] == barcode

    async def test_combines_brand_and_product_name(self):
        """Should combine brand and product name with quantity."""
        barcode = "5901234123457"
        mock_off_data = {
            "code": barcode,
            "status": 1,
            "product": {
                "product_name": "Whole Milk",
                "brands": "Valio",
                "quantity": "1L",
            },
        }

        with patch("app.services.off_service.fetch_product_from_off", return_value=mock_off_data):
            result = await enrich_product_from_off(barcode)

            assert result["canonical_name"] == "Valio Whole Milk 1L"

    async def test_handles_missing_quantity(self):
        """Should handle products without quantity."""
        barcode = "5901234123457"
        mock_off_data = {
            "code": barcode,
            "status": 1,
            "product": {
                "product_name": "Test Product",
                "brands": "Test Brand",
            },
        }

        with patch("app.services.off_service.fetch_product_from_off", return_value=mock_off_data):
            result = await enrich_product_from_off(barcode)

            assert result["canonical_name"] == "Test Brand Test Product"

    async def test_propagates_not_found_error(self):
        """Should propagate OffProductNotFoundError."""
        barcode = "0000000000000"

        with patch(
            "app.services.off_service.fetch_product_from_off",
            side_effect=OffProductNotFoundError(barcode),
        ):
            with pytest.raises(OffProductNotFoundError):
                await enrich_product_from_off(barcode)

    async def test_propagates_api_error(self):
        """Should propagate OffApiError."""
        barcode = "5901234123457"

        with patch(
            "app.services.off_service.fetch_product_from_off",
            side_effect=OffApiError("Network error"),
        ):
            with pytest.raises(OffApiError):
                await enrich_product_from_off(barcode)
