"""Service for Open Food Facts API integration."""

import re
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.services.units import canonical_factor, to_canonical_decimal

# Matches the leading number and optional unit in an OFF quantity string.
# e.g. "1 L", "500g", "33 cl", "1,5 L", "6 x 250 ml" (matches first group)
_QTY_RE = re.compile(
    r"(?P<n>\d+(?:[.,]\d+)?)\s*(?P<u>ml|cl|dl|l|g|kg|oz|fl\.?\s*oz)?",
    re.IGNORECASE,
)


class OffProductNotFoundError(Exception):
    """Raised when a product is not found in Open Food Facts database."""

    def __init__(self, barcode: str):
        self.barcode = barcode
        super().__init__(f"Product {barcode} not found in Open Food Facts database")


class OffApiError(Exception):
    """Raised when Open Food Facts API request fails."""

    pass


async def fetch_product_from_off(barcode: str) -> dict[str, Any]:
    """Fetch product data from Open Food Facts API.

    Args:
        barcode: Product barcode (EAN-13, UPC, etc.).

    Returns:
        Product data from OFF API.

    Raises:
        OffProductNotFoundError: If product not found in OFF database.
        OffApiError: If API request fails.
    """
    url = f"{settings.OPENFOODFACTS_API_URL}/product/{barcode}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            # Check if product exists (status=1 means found, status=0 means not found)
            if data.get("status") == 0:
                raise OffProductNotFoundError(barcode)

            return data

    except OffProductNotFoundError:
        # Re-raise our custom exception
        raise
    except httpx.HTTPStatusError as e:
        raise OffApiError(
            f"Failed to fetch product {barcode}: HTTP {e.response.status_code}"
        ) from e
    except Exception as e:
        raise OffApiError(f"Failed to fetch product {barcode}: {str(e)}") from e


def map_off_category_to_system(off_category: str | None) -> str:
    """Map Open Food Facts category to system category.

    Args:
        off_category: Category string from OFF (can be comma-separated).

    Returns:
        System category ID (dairy, meat, produce, etc.).
    """
    if not off_category:
        return "pantry"

    # Convert to lowercase for case-insensitive matching
    category_lower = off_category.lower()

    # Frozen (check first before produce, as "frozen vegetables" should be frozen)
    if "frozen" in category_lower:
        return "frozen"

    # Dairy products
    if any(
        keyword in category_lower
        for keyword in [
            "dairy",
            "milk",
            "cheese",
            "yogurt",
            "yoghurt",
            "cream",
            "butter",
        ]
    ):
        return "dairy"

    # Meat products
    if any(
        keyword in category_lower
        for keyword in ["meat", "chicken", "beef", "pork", "poultry", "sausage", "ham"]
    ):
        return "meat"

    # Seafood. The seeded category is `fish`; returning `seafood` inserted a
    # product whose category foreign key pointed at nothing (H05).
    if any(
        keyword in category_lower for keyword in ["fish", "seafood", "salmon", "tuna"]
    ):
        return "fish"

    # Produce (fruits and vegetables)
    if any(
        keyword in category_lower
        for keyword in ["fruit", "vegetable", "produce", "fresh"]
    ):
        return "produce"

    # Bakery; the seeded category is `bread`.
    if any(keyword in category_lower for keyword in ["bread", "bakery", "pastry"]):
        return "bread"

    # Beverages
    if any(
        keyword in category_lower
        for keyword in ["beverage", "drink", "juice", "soda", "water", "tea", "coffee"]
    ):
        return "beverages"

    # Snacks
    if any(
        keyword in category_lower for keyword in ["snack", "chip", "candy", "chocolate"]
    ):
        return "snacks"

    # Condiments
    if any(
        keyword in category_lower
        for keyword in ["sauce", "condiment", "ketchup", "mustard", "mayonnaise"]
    ):
        return "condiments"

    # Grains; there is no seeded grains category, and dry goods keep for months,
    # which is what `pantry` means here.
    if any(
        keyword in category_lower for keyword in ["grain", "rice", "pasta", "cereal"]
    ):
        return "pantry"

    # Default to pantry for unknown categories
    return "pantry"


def parse_off_quantity(quantity_str: str | None) -> tuple[Decimal | None, str]:
    """Parse an OFF quantity string into a (amount, unit) pair.

    Normalises to the canonical units (DEC-1, MVP-U1) via ``app.services.units``: L→dl (×10),
    cl→dl (×0.1), ml→dl (×0.01), kg→g (×1000). Returns (None, "pcs") when the string is
    absent, empty, or contains no recognisable unit.

    Args:
        quantity_str: Raw quantity string from OFF, e.g. "1 L", "500g", "33 cl".

    Returns:
        Tuple of (Decimal amount or None, unit string).
    """
    if not quantity_str:
        return None, "pcs"

    m = _QTY_RE.search(quantity_str)
    if not m:
        return None, "pcs"

    raw = Decimal(m.group("n").replace(",", "."))
    unit_raw = (m.group("u") or "").lower().replace(" ", "").replace(".", "")

    if unit_raw not in {"l", "cl", "dl", "ml", "kg", "g"}:
        # oz / fl oz and bare counts: not a measurable pack size in system units
        return None, "pcs"
    _, canonical = canonical_factor(unit_raw)
    return to_canonical_decimal(raw, unit_raw), canonical


async def enrich_product_from_off(barcode: str) -> dict[str, Any]:
    """Enrich product data by fetching from Open Food Facts.

    Args:
        barcode: Product barcode.

    Returns:
        Dictionary with enriched product data ready for product_master:
        - canonical_name: Constructed from brand + product_name + quantity
        - category: Mapped system category
        - off_product_id: The barcode
        - off_data: Full product data from OFF for caching
        - default_quantity: Parsed numeric quantity (or None)
        - default_unit: Canonical unit string ("dl", "g", or "pcs")

    Raises:
        OffProductNotFoundError: If product not found in OFF.
        OffApiError: If API request fails.
    """
    # Fetch data from OFF
    off_response = await fetch_product_from_off(barcode)
    product_data = off_response.get("product", {})

    # Extract relevant fields
    product_name = product_data.get("product_name", "Unknown Product")
    brand = product_data.get("brands", "")
    quantity_str = product_data.get("quantity", "")
    categories = product_data.get("categories", "")

    # Construct canonical name
    # Check if product_name already contains the brand to avoid duplication
    name_parts = []
    product_name_lower = product_name.lower() if product_name else ""
    brand_lower = brand.lower() if brand else ""

    if brand and brand_lower not in product_name_lower:
        name_parts.append(brand)
    if product_name:
        name_parts.append(product_name)
    if quantity_str:
        name_parts.append(quantity_str)

    canonical_name = " ".join(name_parts) if name_parts else "Unknown Product"

    # Map category
    system_category = map_off_category_to_system(categories)

    # Parse quantity into amount + unit
    default_quantity, default_unit = parse_off_quantity(quantity_str)

    return {
        "canonical_name": canonical_name,
        "category": system_category,
        "off_product_id": barcode,
        "off_data": product_data,
        "default_quantity": default_quantity,
        "default_unit": default_unit,
    }
