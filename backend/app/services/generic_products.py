"""Generic product rules shared by receipt confirm (MVP-R2) and quick add (MVP-S3).

Products are generic (operator ruling 2026-09-14): one product per thing a household buys, never
per brand, size or cut. A requested name reuses an existing product case-insensitively; a new
product takes its shelf life and storage from its category.
"""

from datetime import date
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.category import get_category
from app.crud.product_master import MovedInventoryItem
from app.models.category import Category
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.expiry_recompute import (
    recompute_expiry_for_products,
    sealed_expiry,
)
from app.services.product_names import (
    learn_product_name,
    normalize_product_name,
    product_for_name,
)
from app.services.storage import location_for_storage, storage_type_for_category
from app.services.units import grams_to_pieces, pieces_to_grams, unit_type_for


class InvalidProductRequest(ValueError):
    """The request names no usable product (unknown id, missing or unknown category)."""


class UnknownProduct(InvalidProductRequest):
    """The request's ``product_id`` names no product.

    A subclass, so every caller that refuses an ``InvalidProductRequest`` still does; the
    agents' stock add tells it apart to answer 404 ``not_found`` like stock consume.
    """


def tidy_name(name: str | None) -> str:
    return " ".join((name or "").split())


class ProductResolver:
    """Find or create generic products; caches within one transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._by_name: dict[str, ProductMaster] = {}
        self._categories: dict[str, Category | None] = {}
        # Stock whose expiry moved because a placeholder was replaced (Q19), for the
        # caller to broadcast once its transaction has committed.
        self.moved: list[MovedInventoryItem] = []

    async def _category(self, category_id: str) -> Category | None:
        if category_id not in self._categories:
            self._categories[category_id] = await get_category(self.db, category_id)
        return self._categories[category_id]

    @staticmethod
    def _fill_gaps(
        product: ProductMaster,
        *,
        piece_grams: float | None = None,
        opened_shelf_life_days: int | None = None,
        pack_grams: float | None = None,
        shelf_life_days: int | None = None,
    ) -> ProductMaster:
        """Learn what is still unknown about a product, never overwrite what is known.

        A later receipt filling in a missing piece weight is useful; the same receipt undoing
        a correction every week is not (Q2).

        Shelf life is the one field that cannot say "unknown" - the column is NOT NULL, so
        creation had to put the category's blanket figure there. `shelf_life_source` says
        which it was, so a placeholder can be improved while a correction stays put (Q11).
        An estimate never replaces another estimate: that would be the weekly churn Q2
        ruled out, and no product needs it.
        """
        if shelf_life_days and str(product.shelf_life_source) == "category":
            product.default_shelf_life_days = shelf_life_days
            product.shelf_life_source = "model"
        if piece_grams and product.avg_piece_grams is None:
            product.avg_piece_grams = Decimal(str(piece_grams))
        if opened_shelf_life_days and product.opened_shelf_life_days is None:
            product.opened_shelf_life_days = opened_shelf_life_days
        if pack_grams and product.pack_grams is None:
            product.pack_grams = Decimal(str(pack_grams))
        return product

    async def _learn(
        self,
        product: ProductMaster,
        *,
        piece_grams: float | None = None,
        opened_shelf_life_days: int | None = None,
        pack_grams: float | None = None,
        shelf_life_days: int | None = None,
    ) -> ProductMaster:
        """`_fill_gaps`, and the stock it dated moves when the shelf life was replaced.

        Replacing a placeholder used to leave the items it dated at the old expiry (Q19):
        the product said 720 days while the crispbread in the cupboard still said 10.
        """
        before = int(product.default_shelf_life_days)
        self._fill_gaps(
            product,
            piece_grams=piece_grams,
            opened_shelf_life_days=opened_shelf_life_days,
            pack_grams=pack_grams,
            shelf_life_days=shelf_life_days,
        )
        if int(product.default_shelf_life_days) != before:
            self.moved.extend(await recompute_expiry_for_products(self.db, [product]))
        return product

    async def resolve(
        self,
        *,
        unit: str | None = None,
        quantity: Decimal | float,
        product_id: UUID | None = None,
        name: str | None = None,
        category: str | None = None,
        piece_grams: float | None = None,
        pack_grams: float | None = None,
        shelf_life_days: int | None = None,
        opened_shelf_life_days: int | None = None,
        trust_model_names: bool = True,
    ) -> tuple[ProductMaster, bool]:
        """Return ``(product, created)``.

        ``trust_model_names=False`` makes a typed name skip synonyms the model taught
        (H51): the cook naming a product has refused whatever was proposed for the line.
        The per-transaction cache is keyed by name alone, so two lines typed with the
        same name on one receipt share the first outcome; harmless, and rare.

        Raises:
            UnknownProduct: unknown ``product_id`` (an ``InvalidProductRequest``).
            InvalidProductRequest: no name, or a new product without a valid category.
        """
        if product_id is not None:
            product = await self.db.get(ProductMaster, product_id)
            if product is None:
                raise UnknownProduct(f"product '{product_id}' not found")
            return (
                await self._learn(
                    product,
                    piece_grams=piece_grams,
                    opened_shelf_life_days=opened_shelf_life_days,
                    pack_grams=pack_grams,
                    shelf_life_days=shelf_life_days,
                ),
                False,
            )

        tidy = tidy_name(name)
        if not tidy:
            raise InvalidProductRequest("no product name")
        key = normalize_product_name(tidy)
        if key in self._by_name:
            return (
                await self._learn(
                    self._by_name[key],
                    piece_grams=piece_grams,
                    opened_shelf_life_days=opened_shelf_life_days,
                    pack_grams=pack_grams,
                    shelf_life_days=shelf_life_days,
                ),
                False,
            )

        # Any known name, not just the canonical one: "Minced beef" finds Ground beef
        # once a confirm has learned the synonym (spec §3.1).
        existing = await product_for_name(self.db, tidy, trust_model=trust_model_names)
        if existing is not None:
            self._by_name[key] = existing
            return (
                await self._learn(
                    existing,
                    piece_grams=piece_grams,
                    opened_shelf_life_days=opened_shelf_life_days,
                    pack_grams=pack_grams,
                    shelf_life_days=shelf_life_days,
                ),
                False,
            )

        if not category:
            raise InvalidProductRequest(f"Category required for new product '{tidy}'")
        category_row = await self._category(category)
        if category_row is None:
            raise InvalidProductRequest(
                f"Unknown category '{category}' for new product '{tidy}'"
            )

        # Knowing what one weighs means the cook counts them, whatever the receipt
        # printed (Q2); knowing what a pack weighs means the cook measures it, whatever
        # the receipt counted (Q8). A piece weight wins: a 500 g bag of onions is still
        # onions.
        if piece_grams:
            natural_unit = "pcs"
        elif pack_grams:
            natural_unit = "g"
        else:
            # Nothing to resolve to and nothing said: one of a thing (H25). Only quick add
            # reaches this without a unit; a receipt line always printed one.
            natural_unit = unit or "pcs"
        product = ProductMaster(
            # Hand-typed names ("oat drink") read like extracted generic names ("Oat drink")
            canonical_name=tidy[:1].upper() + tidy[1:],
            category=category_row.id,
            storage_type=storage_type_for_category(str(category_row.id)),
            # What this product keeps for, falling back to its category's blanket figure (Q6)
            default_shelf_life_days=shelf_life_days
            or category_row.default_shelf_life_days,
            # ...and which of those two it was, so a fallback can be improved later and a
            # real answer cannot be trampled (Q11)
            shelf_life_source="model" if shelf_life_days else "category",
            avg_piece_grams=piece_grams,
            pack_grams=pack_grams,
            # How long it keeps once the pack is open, when the model could say (Q5)
            opened_shelf_life_days=opened_shelf_life_days,
            unit_type=unit_type_for(natural_unit),
            default_unit=natural_unit,
            default_quantity=quantity,
        )
        self.db.add(product)
        await self.db.flush()
        # The canonical name is a row like any other, so the next lookup is one query.
        await learn_product_name(
            self.db, product, str(product.canonical_name), "canonical"
        )
        self._by_name[key] = product
        return product, True


def quantity_for_product(
    product: ProductMaster, quantity: Decimal | float, unit: str
) -> tuple[Decimal | float, str]:
    """Store the amount the way this product is counted.

    Two mirrored conversions:

    - a receipt weighs the apples and the cook eats them one at a time, so a weighed
      line for a product with a known piece weight is stored in pieces (Q2/Q3);
    - a receipt counts packs of mince and the cook wants to know there is 400 g in the
      freezer, so a counted line for a product with a known pack weight is stored in
      grams (Q8).

    Anything else is left alone.
    """
    if unit == "g" and str(product.default_unit) == "pcs":
        pieces = grams_to_pieces(
            quantity, cast(Decimal | None, product.avg_piece_grams)
        )
        return (pieces, "pcs") if pieces is not None else (quantity, unit)

    if unit == "pcs" and str(product.default_unit) == "g":
        grams = pieces_to_grams(quantity, cast(Decimal | None, product.pack_grams))
        return (grams, "g") if grams is not None else (quantity, unit)

    return quantity, unit


def build_inventory_item(
    product: ProductMaster,
    *,
    quantity: Decimal | float,
    unit: str | None = None,
    purchase_date: date,
    expiry_date: date | None = None,
    location: str | None = None,
    receipt_id: UUID | None = None,
) -> InventoryItem:
    """A sealed item: unit, expiry and location come from the product unless overridden.

    The unit is the product's own when the caller did not name one (H25): quick add resolves a
    typed name to a product the client cannot see, so its guess would be about the wrong thing.
    """
    quantity, unit = quantity_for_product(
        product, quantity, unit or str(product.default_unit)
    )
    if expiry_date is not None:
        expiry, source = expiry_date, "manual"
    else:
        expiry = sealed_expiry(product, purchase_date)
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
