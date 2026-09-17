"""Generic product rules shared by receipt confirm (MVP-R2) and quick add (MVP-S3).

Products are generic (operator ruling 2026-09-14): one product per thing a household buys, never
per brand, size or cut. A requested name reuses an existing product case-insensitively; a new
product takes its shelf life and storage from its category.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.category import get_category
from app.models.category import Category
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.storage import location_for_storage, storage_type_for_category
from app.services.units import grams_to_pieces, unit_type_for


class InvalidProductRequest(ValueError):
    """The request names no usable product (unknown id, missing or unknown category)."""


def tidy_name(name: str | None) -> str:
    return " ".join((name or "").split())


class ProductResolver:
    """Find or create generic products; caches within one transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._by_name: dict[str, ProductMaster] = {}
        self._categories: dict[str, Category | None] = {}

    async def _category(self, category_id: str) -> Category | None:
        if category_id not in self._categories:
            self._categories[category_id] = await get_category(self.db, category_id)
        return self._categories[category_id]

    @staticmethod
    def _fill_gaps(product: ProductMaster, piece_grams: float | None) -> ProductMaster:
        """Learn what is still unknown about a product, never overwrite what is known.

        A later receipt filling in a missing piece weight is useful; the same receipt undoing
        a correction every week is not (Q2).
        """
        if piece_grams and product.avg_piece_grams is None:
            product.avg_piece_grams = Decimal(str(piece_grams))
        return product

    async def resolve(
        self,
        *,
        unit: str,
        quantity: Decimal | float,
        product_id: UUID | None = None,
        name: str | None = None,
        category: str | None = None,
        piece_grams: float | None = None,
        shelf_life_days: int | None = None,
    ) -> tuple[ProductMaster, bool]:
        """Return ``(product, created)``.

        Raises:
            InvalidProductRequest: unknown ``product_id``, no name, or a new product without a
                valid category.
        """
        if product_id is not None:
            product = await self.db.get(ProductMaster, product_id)
            if product is None:
                raise InvalidProductRequest(f"product '{product_id}' not found")
            return self._fill_gaps(product, piece_grams), False

        tidy = tidy_name(name)
        if not tidy:
            raise InvalidProductRequest("no product name")
        key = tidy.casefold()
        if key in self._by_name:
            return self._fill_gaps(self._by_name[key], piece_grams), False

        existing = (
            (
                await self.db.execute(
                    select(ProductMaster)
                    .where(func.lower(ProductMaster.canonical_name) == tidy.lower())
                    .order_by(ProductMaster.created_at)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            self._by_name[key] = existing
            return self._fill_gaps(existing, piece_grams), False

        if not category:
            raise InvalidProductRequest(f"Category required for new product '{tidy}'")
        category_row = await self._category(category)
        if category_row is None:
            raise InvalidProductRequest(
                f"Unknown category '{category}' for new product '{tidy}'"
            )

        # Knowing what one weighs means the cook counts them, whatever the receipt printed (Q2)
        natural_unit = "pcs" if piece_grams else unit
        product = ProductMaster(
            # Hand-typed names ("oat drink") read like extracted generic names ("Oat drink")
            canonical_name=tidy[:1].upper() + tidy[1:],
            category=category_row.id,
            storage_type=storage_type_for_category(str(category_row.id)),
            # What this product keeps for, falling back to its category's blanket figure (Q6)
            default_shelf_life_days=shelf_life_days
            or category_row.default_shelf_life_days,
            avg_piece_grams=piece_grams,
            unit_type=unit_type_for(natural_unit),
            default_unit=natural_unit,
            default_quantity=quantity,
        )
        self.db.add(product)
        await self.db.flush()
        self._by_name[key] = product
        return product, True


def quantity_for_product(
    product: ProductMaster, quantity: Decimal | float, unit: str
) -> tuple[Decimal | float, str]:
    """Store the amount the way this product is counted.

    A receipt weighs the apples and the cook eats them one at a time, so a weighed line for a
    product with a known piece weight is stored in pieces (Q2/Q3). Anything else is left alone.
    """
    if unit != "g" or str(product.default_unit) != "pcs":
        return quantity, unit
    pieces = grams_to_pieces(quantity, cast(Decimal | None, product.avg_piece_grams))
    return (pieces, "pcs") if pieces is not None else (quantity, unit)


def build_inventory_item(
    product: ProductMaster,
    *,
    quantity: Decimal | float,
    unit: str,
    purchase_date: date,
    expiry_date: date | None = None,
    location: str | None = None,
    receipt_id: UUID | None = None,
) -> InventoryItem:
    """A sealed item: expiry and location come from the product unless overridden."""
    quantity, unit = quantity_for_product(product, quantity, unit)
    if expiry_date is not None:
        expiry, source = expiry_date, "manual"
    else:
        expiry = purchase_date + timedelta(days=int(product.default_shelf_life_days))
        source = "calculated"
    return InventoryItem(
        product_master_id=product.id,
        receipt_id=receipt_id,
        initial_quantity=quantity,
        current_quantity=quantity,
        unit=unit,
        status="sealed",
        purchase_date=purchase_date,
        expiry_date=expiry,
        expiry_source=source,
        location=location or location_for_storage(str(product.storage_type)),
    )
