"""Auto-add to the shopping list once a product's active stock drops below its minimum.

Reuses AG6's own rules (`services.shopping_generate`) instead of restating them: the same
"is it low" test (active stock below `min_stock_quantity`, converted into the product's
unit) and the same amount (`reorder_quantity`, or the shortfall when none is set). The
difference is *when* it runs - once, right after whatever lowered the stock, for the one
product that changed - rather than for every product on demand.

`after_stock_decrease` is the one entry point every such change calls, once it has
committed: the iPad's `/inventory/{id}/consume` and its `PATCH .../{id}` (discarded, or a
corrected amount that is lower), its bulk `/inventory/discard`, the agent's and Home
Assistant's `/stock/consume` (both share `services.stock.consume`), and the barcode
scanner's consume mode. It never raises and it broadcasts its own `shopping_list_update`
(F2): the stock change has already committed by the time this runs, so a failure here -
a locked row, a dropped connection - must never turn an otherwise-successful request into
a 500, and nothing else is left to broadcast it if this does not.

The advisory lock it takes (AG6's own `GENERATE_LOCK`) is deliberately the *same* lock
`shopping_generate.generate` takes, not one of this module's own (F4): both decide whether
to add or raise an item for a product from the same "is it low" read of the open list, so
a consumption racing an on-demand `/shopping/generate` - not just two consumptions of the
same product - must serialise on one lock between them, or both could find the open list
empty and both add.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.crud.shopping_list_item import shopping_list_item as crud_shopping
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem
from app.schemas.shopping_list_item import (
    ShoppingListItemCreate,
    ShoppingPriority,
    ShoppingSource,
)
from app.services.broadcast_helpers import broadcast_shopping_list_update
from app.services.units import quantise

# `shopping_generate` itself imports `stock_summary` from `services.stock`, and `stock.py`
# imports this module - a module-level import of `shopping_generate` here would be
# circular. Deferred to call time instead, by which point both modules are fully loaded.

logger = get_logger(__name__)


async def _on_hand(db: AsyncSession, product: Any) -> Decimal | None:
    """Active stock for `product`, in its own unit; None when some of it is in a unit
    that does not convert there - AG6 skips such a product rather than guess, and this
    does the same."""
    from app.services.shopping_generate import _factor
    from app.services.shopping_generate import _Incompatible as Incompatible

    unit = str(product.default_unit)
    # Any: the models declare untyped `Column`s, which mypy reads as Column[...], not values.
    items: list[Any] = await crud_inventory.get_active_items_by_product(db, product.id)
    total = Decimal(0)
    for item in items:
        try:
            total += Decimal(item.current_quantity) * _factor(str(item.unit), unit)
        except Incompatible:
            return None
    return total


async def _has_open_item(db: AsyncSession, product: Any) -> bool:
    """An open item already speaks for `product` - linked, or free-text under the same
    name (F3): a cook who typed "Milk" by hand meant the same trip to the shop a linked
    item would, so a second, linked one must not pile on beside it. Compared normalised
    (stripped, casefolded) in Python rather than with SQL `lower()`, so it agrees with
    every other place names are matched this way (`ProductName.name`'s own casefold)."""
    linked = await crud_shopping.get_by_product(db, product_master_id=product.id)
    if linked:
        return True

    name_key = str(product.canonical_name).strip().casefold()
    rows = await db.execute(
        select(ShoppingListItem.name).where(
            ShoppingListItem.product_master_id.is_(None),
            ShoppingListItem.is_purchased.is_(False),
        )
    )
    return any(str(name).strip().casefold() == name_key for (name,) in rows.all())


async def maybe_auto_add(db: AsyncSession, product: Any) -> ShoppingListItem | None:
    """Add one open item for `product` once its active stock is below its minimum.

    Manages its own transaction on `db` (commits what it adds, or rolls back and
    re-raises on failure), so any caller can call it right after its own change has
    committed: the product passed in need only be the row as the caller already has it -
    `id`, `min_stock_quantity`, `reorder_quantity`, `default_unit` and `canonical_name` are
    the only fields read.

    Does nothing (and still commits, to release the advisory lock promptly) when: the
    product has no minimum; its stock (as `_on_hand` can compute it) is still at or above
    that minimum; an open item for it already exists, manual or auto, linked or free-text
    (`_has_open_item`); or the computed amount is not positive. Otherwise adds one item
    with AG6's own `auto_restock` source and amount rule.

    Returns the item added, for the caller to broadcast `shopping_list_update` with; None
    when nothing changed. Raises on failure - `after_stock_decrease` is the entry point
    that never does; this one is for tests and for callers that want to handle it
    themselves.
    """
    from app.services.shopping_generate import GENERATE_LOCK

    min_stock = product.min_stock_quantity
    if min_stock is None:
        return None
    min_stock = Decimal(min_stock)

    try:
        # Only a product that might actually need adding pays for the lock - a consume of
        # a product with no minimum (checked above, before this) never contends for it.
        await db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(GENERATE_LOCK, 0)))
        )

        on_hand = await _on_hand(db, product)
        if on_hand is None or on_hand >= min_stock:
            await db.commit()
            return None

        if await _has_open_item(db, product):
            await db.commit()
            return None

        reorder = product.reorder_quantity
        need = quantise(
            Decimal(reorder) if reorder is not None else min_stock - on_hand
        )
        if need <= 0:
            await db.commit()
            return None

        item = await crud_shopping.stage(
            db,
            obj_in=ShoppingListItemCreate(
                product_master_id=product.id,
                name=str(product.canonical_name),
                quantity=need,
                unit=str(product.default_unit),
                priority=ShoppingPriority.NORMAL,
                source=ShoppingSource.AUTO_RESTOCK,
            ),
        )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Auto-added to shopping list below minimum stock",
        extra={
            "product_id": str(product.id),
            "quantity": str(need),
            "unit": str(product.default_unit),
        },
    )
    return item


async def after_stock_decrease(db: AsyncSession, product_id: UUID) -> None:
    """Call this once, after any change that lowers a product's active stock has
    committed: a consume (the iPad, the agent, Home Assistant, the barcode scanner), a
    `PATCH` that discards an item or corrects its quantity down, or a bulk discard.

    Reloads the product by id - every caller has at least this - and broadcasts
    `shopping_list_update` itself when `maybe_auto_add` adds something, so callers need
    nothing back (F2: nothing is left undone if a caller forgot to check a return value).
    Never raises: the stock change this follows has already committed, so a failure
    deciding whether to put something back on the shopping list - a locked row, a dropped
    connection - must never turn an otherwise-successful request into a 500. Logged at
    WARNING rather than silently swallowed.
    """
    try:
        product = await db.get(ProductMaster, product_id)
        if product is None:
            return
        # Any: the models declare untyped `Column`s, which mypy reads as Column[...], not
        # values.
        added: Any = await maybe_auto_add(db, product)
    except Exception:
        logger.warning(
            "Auto-add after a stock decrease failed; the stock change itself is"
            " unaffected",
            exc_info=True,
            extra={"product_id": str(product_id)},
        )
        return

    if added is None:
        return
    await broadcast_shopping_list_update(
        shopping_list_item_id=added.id,
        action="created",
        name=added.name,
        quantity=added.quantity,
        unit=added.unit,
        priority=added.priority,
        is_purchased=False,
    )
