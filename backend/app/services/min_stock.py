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

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NamedTuple, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.crud.shopping_list_item import shopping_list_item as crud_shopping
from app.domain.units import quantise
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem
from app.schemas.shopping_list_item import (
    ShoppingListItemCreate,
    ShoppingPriority,
    ShoppingSource,
)
from app.services.broadcast_helpers import broadcast_shopping_list_update
from app.services.undo import RaisedStock

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


async def maybe_retract(
    db: AsyncSession,
    product: Any,
    *,
    since: datetime,
    raised_unit: str,
    raised_amount: Decimal,
) -> ShoppingListItem | None:
    """Undo's mirror of `maybe_auto_add` (A4): take back one open `auto_restock` item for
    `product`, added after `since` (the undone batch's earliest log row, so an item from
    an older, unrelated drop survives), once an undo has raised the product's active
    stock back to, or above, its minimum.

    Manages its own transaction exactly as `maybe_auto_add` does: commits what it removes,
    or when it finds nothing to do (to release the advisory lock promptly), and rolls back
    and re-raises on failure.

    Does nothing when: the product has no minimum; its stock (`_on_hand`) is still below
    that minimum, or cannot be read; no open, unpurchased `auto_restock` item for it was
    added after `since`; or the one found does not match what `maybe_auto_add` would have
    set - the only way to tell, with no stored "edited" flag, that the cook has since
    changed its quantity (F1's ruling; a manual or purchased item is excluded earlier, by
    `source` and `get_by_product`'s own `is_purchased` filter). A product with a
    `reorder_quantity` is compared against that directly, since it does not depend on how
    low the stock was; without one, the shortfall `maybe_auto_add` would have set is
    reconstructed from the stock as it was just before this undo raised it - `on_hand -
    raised_amount`, converted into the product's unit - against which an item the cook
    has not touched still matches exactly. Unreconstructable (an incompatible unit) is
    treated the same as a mismatch: left alone.

    Returns the item removed, for the caller to broadcast `shopping_list_update` with;
    None when nothing changed. Raises on failure - `after_stock_increase_by_undo` is the
    entry point that never does.
    """
    from app.services.shopping_generate import GENERATE_LOCK, _factor
    from app.services.shopping_generate import _Incompatible as Incompatible

    min_stock = product.min_stock_quantity
    if min_stock is None:
        return None
    min_stock = Decimal(min_stock)

    try:
        # Same lock `maybe_auto_add` takes (F4): an undo racing a consume, or an on-demand
        # generate, must see the other's committed change rather than a stale read.
        await db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(GENERATE_LOCK, 0)))
        )

        on_hand = await _on_hand(db, product)
        if on_hand is None or on_hand < min_stock:
            await db.commit()
            return None

        candidates = [
            item
            for item in await crud_shopping.get_by_product(
                db, product_master_id=product.id
            )
            if str(item.source) == ShoppingSource.AUTO_RESTOCK and item.added_at > since
        ]
        if not candidates:
            await db.commit()
            return None
        target = candidates[0]

        reorder = product.reorder_quantity
        if reorder is not None:
            expected: Decimal | None = Decimal(reorder)
        else:
            try:
                raised_in_unit: Decimal | None = raised_amount * _factor(
                    raised_unit, str(product.default_unit)
                )
            except Incompatible:
                raised_in_unit = None
            expected = (
                quantise(min_stock - (on_hand - raised_in_unit))
                if raised_in_unit is not None
                else None
            )

        if expected is None or Decimal(str(target.quantity)) != expected:
            await db.commit()
            return None

        # Captured before the delete, for the caller's broadcast - `remove` re-reads by
        # id and, once deleted, there is nothing left to read the fields back from.
        removed = target
        # `CRUDBase.remove`'s `id` is typed `int` (crud/base.py is shared, read-only
        # here); every id here is actually a `UUID`, as `shopping.py`'s own delete
        # already passes one.
        await crud_shopping.remove(db, id=cast(Any, target.id))
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Retracted an auto-added shopping item after an undo raised stock back to the"
        " minimum",
        extra={
            "product_id": str(product.id),
            "shopping_list_item_id": str(removed.id),
        },
    )
    return removed


async def after_stock_increase_by_undo(
    db: AsyncSession, raised: Sequence[RaisedStock], since: datetime
) -> None:
    """Call this once, after an undo has committed, with every item whose restore raised
    its product's active stock (`services.undo.RaisedStock`) and the undone batch's
    earliest log row (`since`), for the undo endpoint.

    One call into `maybe_retract` per distinct product: several items of the same product
    in one undone batch (a bulk discard's undo) are summed first, in that product's own
    unit, the same way `_on_hand` counts them.

    Never raises and broadcasts its own `shopping_list_update` for each item taken back,
    for the same reason `after_stock_decrease` does not: the undo has already committed
    by the time this runs, so a failure here - a locked row, a dropped connection - must
    never turn an otherwise-successful undo into a 500. Logged at WARNING rather than
    silently swallowed.
    """
    totals: dict[UUID, Decimal] = {}
    units: dict[UUID, str] = {}
    for entry in raised:
        totals[entry.product_id] = (
            totals.get(entry.product_id, Decimal(0)) + entry.amount
        )
        units.setdefault(entry.product_id, entry.unit)

    for product_id, amount in totals.items():
        try:
            product = await db.get(ProductMaster, product_id)
            if product is None:
                continue
            # Any: the models declare untyped `Column`s, which mypy reads as
            # Column[...], not values.
            removed: Any = await maybe_retract(
                db,
                product,
                since=since,
                raised_unit=units[product_id],
                raised_amount=amount,
            )
        except Exception:
            logger.warning(
                "Retracting an auto-added item after an undo failed; the undo itself"
                " is unaffected",
                exc_info=True,
                extra={"product_id": str(product_id)},
            )
            continue

        if removed is None:
            continue
        await broadcast_shopping_list_update(
            shopping_list_item_id=removed.id,
            action="deleted",
            name=removed.name,
            quantity=removed.quantity,
            unit=removed.unit,
            priority=removed.priority,
            is_purchased=None,
        )


class BoughtItem(NamedTuple):
    """What `after_stock_increase`'s broadcast carries for one item `mark_bought`
    ticked - read before the commit, so nothing has to be reloaded afterwards."""

    id: UUID
    name: str
    quantity: Decimal
    unit: str
    priority: str


async def mark_bought(db: AsyncSession, product_id: UUID) -> list[BoughtItem]:
    """Mark every open (unpurchased) shopping item linked to `product_id` purchased,
    whatever its `source` (CL2): new stock of the product is what those items were for.
    A free-text item is never touched - it has no product to match - and an item already
    bought keeps its own `purchased_at`. Quantities are not compared: an item is closed
    whatever amount it asked for.

    Manages its own transaction exactly as `maybe_auto_add` does, under the same
    `GENERATE_LOCK`, so a restock racing a consume's auto-add, or an on-demand generate,
    sees the other's committed item rather than a stale read: commits what it marks (or,
    when there is nothing, to release the lock promptly), and rolls back and re-raises on
    failure.

    Returns the items marked, for the caller to broadcast `shopping_list_update` with.
    Raises on failure - `after_stock_increase` is the entry point that never does.
    """
    from app.services.shopping_generate import GENERATE_LOCK

    try:
        await db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(GENERATE_LOCK, 0)))
        )
        # `get_by_product` already filters to linked, unpurchased items.
        # Any: the models declare untyped `Column`s, which mypy reads as Column[...],
        # not values.
        items: list[Any] = await crud_shopping.get_by_product(
            db, product_master_id=product_id
        )
        now = datetime.now(UTC)
        bought = []
        for item in items:
            item.is_purchased = True
            item.purchased_at = now
            bought.append(
                BoughtItem(item.id, item.name, item.quantity, item.unit, item.priority)
            )
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    return bought


async def after_stock_increase(db: AsyncSession, product_ids: Sequence[UUID]) -> None:
    """Call this once, after any change that adds new stock has committed - a receipt
    confirm, the iPad's quick add, the agent's `/stock/add` - with the product of every
    item it created (duplicates are handled once).

    Marks each product's open shopping items purchased (`mark_bought`) and broadcasts one
    `shopping_list_update` per item, with the same `purchased` action the Shopping
    screen's own tick sends. Never raises, for the same reason `after_stock_decrease`
    does not: the stock has already committed by the time this runs, so a failure here -
    a locked row, a dropped connection - must never turn an otherwise-successful request
    into a 500. Logged at WARNING rather than silently swallowed, and one product's
    failure does not stop the next.
    """
    for product_id in dict.fromkeys(product_ids):
        try:
            bought = await mark_bought(db, product_id)
        except Exception:
            logger.warning(
                "Ticking shopping items bought after new stock failed; the stock"
                " change itself is unaffected",
                exc_info=True,
                extra={"product_id": str(product_id)},
            )
            continue

        logger.info(
            "Marked open shopping items bought after new stock",
            extra={"product_id": str(product_id), "count": len(bought)},
        )
        for item in bought:
            await broadcast_shopping_list_update(
                shopping_list_item_id=item.id,
                action="purchased",
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                priority=item.priority,
                is_purchased=True,
            )
