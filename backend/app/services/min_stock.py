"""Auto-add to the shopping list once a consumption leaves a product short.

Reuses AG6's own rules (`services.shopping_generate`) instead of restating them: the same
"is it low" test (active stock below `min_stock_quantity`, converted into the product's
unit) and the same amount (`reorder_quantity`, or the shortfall when none is set). The
difference is *when* it runs - once, right after a consumption, for the one product that
changed - rather than for every product on demand.

Called after a consume has committed, in a transaction of its own: every consume path
(the iPad's `/inventory/{id}/consume`, the agent's and Home Assistant's `/stock/consume`)
already commits before this runs, so the stock it reads already includes the consumption
that triggered it, and a failure here never takes the consume itself back out. It takes
AG6's own advisory lock (`shopping_generate.GENERATE_LOCK`) before it decides anything, so
a second consumption of the same product - or an on-demand `/shopping/generate` - racing
this one serialises behind it rather than both finding the open list empty and both adding
an item: whichever gets the lock first commits before the other reads the open list, and
the loser then finds the item already there.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.crud.shopping_list_item import shopping_list_item as crud_shopping
from app.models.shopping_list_item import ShoppingListItem
from app.schemas.shopping_list_item import (
    ShoppingListItemCreate,
    ShoppingPriority,
    ShoppingSource,
)
from app.services.units import quantise

# `shopping_generate` itself imports `stock_summary` from `services.stock`, and `stock.py`
# imports this module to reach `maybe_auto_add` - a module-level import here would be
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


async def maybe_auto_add(db: AsyncSession, product: Any) -> ShoppingListItem | None:
    """Add one open item for `product` once its active stock is below its minimum.

    Manages its own transaction on `db` (commits what it adds, or rolls back and
    re-raises on failure), so any caller can call it right after its own consume has
    committed: the product passed in need only be the row as the caller already has it -
    `id`, `min_stock_quantity`, `reorder_quantity`, `default_unit` and `canonical_name` are
    the only fields read.

    Does nothing (and still commits, to release the advisory lock promptly) when: the
    product has no minimum; its stock (as `_on_hand` can compute it) is still at or above
    that minimum; an open item for it already exists, manual or auto; or the computed
    amount is not positive. Otherwise adds one item with AG6's own `auto_restock` source
    and amount rule.

    Returns the item added, for the caller to broadcast `shopping_list_update` with; None
    when nothing changed.
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

        open_items = await crud_shopping.get_by_product(
            db, product_master_id=product.id
        )
        if open_items:
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
