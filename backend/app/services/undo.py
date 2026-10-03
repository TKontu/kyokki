"""One general undo: the most recent change to stock, reversed (operator, 2026-09-22).

Built on the consumption log (H46). Every row keeps the item as it was just before the event
(`previous`), and the rows one action wrote share a `batch_id`, so undo is: find the newest
batch, put each item back, and delete the rows - an undone helping was never eaten, and a
waste total must not count it. Pressing it again finds the batch before that.

What it can reach is what the log records: consume, finish, mark as gone, a cleared shelf, a
restore and a quantity correction. Adding an item or moving it to another shelf is not an
event in the log, so it is not a step here; deleting an item deletes its history, and with it
its steps.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import consumption_log as crud_log
from app.crud import inventory_item as crud_inventory
from app.models.inventory_item import InventoryItem
from app.schemas.consumption_log import ConsumptionAction


class UndoConflict(Exception):
    """What the caller asked to undo is not the most recent change any more, or never was."""


@dataclass(frozen=True)
class UndoStep:
    """One row of the batch the next undo would reverse, as the header describes it."""

    inventory_item_id: UUID
    product_name: str
    unit: str
    action: str
    quantity_consumed: Decimal
    direction: Literal["up", "down"] | None = None


@dataclass(frozen=True)
class RaisedStock:
    """How much one undone row's restore raised its product's active stock (A4).

    Only rows that actually raised stock produce one of these (a discard or consume
    undone, or a correction undone upward); a restore's own undo, which re-discards, and
    a correction undone downward do not. The caller (the undo endpoint) hands these to
    `min_stock.after_stock_increase_by_undo`, which decides whether an auto-added item
    for the product can now come back off the list - never this layer's job.
    """

    product_id: UUID
    unit: str
    amount: Decimal


@dataclass(frozen=True)
class UndoResult:
    """What one undo did: the items it put back, for the usual broadcast, and - kept
    separate, since it is a different concern (A4) - what it raised, for the endpoint to
    offer to `min_stock.after_stock_increase_by_undo`."""

    items: list[InventoryItem]
    raised: tuple[RaisedStock, ...] = field(default_factory=tuple)
    since: datetime | None = None


def _left_on_item(row: Any) -> Decimal:
    """The quantity the event left on the item row itself.

    Usually `quantity_after`. A discard is the exception: nothing is left in the kitchen, so
    the log says 0, but the item keeps its quantity frozen (H23) - that is the amount thrown
    away, and what a restore brings back.
    """
    if row.action == ConsumptionAction.DISCARD:
        return Decimal(str(row.quantity_consumed))
    return Decimal(str(row.quantity_after))


def _active_amount(status: Any, quantity: Decimal) -> Decimal:
    """`quantity`, if `status` counts as active stock (H23's own `INACTIVE_STATUSES`);
    zero otherwise - a discarded or emptied item speaks for none of it, however much it
    still carries frozen on the row. What `after_stock_increase_by_undo` compares before
    and after an undo: a discard's own undo raises stock by its full frozen amount
    (inactive to active), not by zero (its `current_quantity` never moves) - and a
    restore's undo (active to inactive) lowers it the same way, by the same amount."""
    if str(status) in crud_inventory.INACTIVE_STATUSES:
        return Decimal(0)
    return quantity


async def _undoable_batch(db: AsyncSession) -> list[Any]:
    # `Any` rows, as elsewhere, until H21 types the models: every column reads as `Column[...]`
    rows: list[Any] = await crud_log.newest_batch(db)
    # A row from before undo existed does not know what it overwrote. It stops the walk back
    # rather than being skipped: undoing something older underneath it would be wrong.
    if not rows or any(row.previous is None for row in rows):
        return []
    # A deleted item keeps its waste record (2026-09-22) but cannot be put back. Skipping to
    # the batch before is safe in a way skipping a `previous IS NULL` row is not: nothing can
    # have happened to an item that no longer exists, so there is no order to get wrong.
    if all(row.inventory_item_id is None for row in rows):
        return await crud_log.newest_batch_before(db, rows[0].batch_id)
    return rows


async def preview(db: AsyncSession) -> tuple[UUID, Any, list[UndoStep]] | None:
    """What the next undo would reverse: its batch id, when it happened, and its steps."""
    rows = await _undoable_batch(db)
    if not rows:
        return None
    steps = [
        UndoStep(
            inventory_item_id=row.inventory_item_id,
            product_name=row.product_name,
            unit=row.unit,
            action=str(row.action),
            quantity_consumed=Decimal(str(row.quantity_consumed)),
            direction=crud_log.correction_direction(row),
        )
        for row in rows
    ]
    return rows[0].batch_id, rows[-1].logged_at, steps


async def undo(db: AsyncSession, batch_id: UUID) -> UndoResult:
    """Reverse the most recent action, if it is the one the caller was shown.

    The id is what makes this safe on a shared kitchen: the iPad showed "Undo: -1 Cream", and
    if the Telegram bot consumed something in between, undoing *that* instead would be a
    surprise. So a stale id is refused, and so is a batch whose items have moved since.

    Raises:
        UndoConflict: Nothing to undo, a newer change came first, or an item moved since.
    """
    rows = await _undoable_batch(db)
    if not rows or rows[0].batch_id != batch_id:
        raise UndoConflict("Something newer has happened since; nothing was undone")

    items = await crud_inventory.lock_inventory_items(
        db, [row.inventory_item_id for row in rows]
    )
    # Read again under the locks: a second undo racing this one has either finished (the rows
    # are gone) or is waiting behind us.
    rows = await _undoable_batch(db)
    if not rows or rows[0].batch_id != batch_id:
        raise UndoConflict("Something newer has happened since; nothing was undone")

    for row in rows:
        item = items.get(row.inventory_item_id)
        current = Decimal(str(item.current_quantity)) if item is not None else None
        if current != _left_on_item(row):
            raise UndoConflict(
                f"{row.product_name} has changed since; nothing was undone"
            )

    # A4: what this undo is about to raise, worked out from the items and log rows as
    # they stand right now - before the loop below mutates them - so the endpoint can
    # offer each product to `min_stock.after_stock_increase_by_undo` once this has
    # committed. Compared as *active* stock (`_active_amount`), not raw quantity: a
    # discard's own undo raises stock by its full frozen amount (the row's
    # `current_quantity` never moves - only its status does, from `discarded` back to
    # active), and a restore's own undo lowers it the same way, by the same amount - so
    # going by quantity alone would miss the one and misread the other as a raise. Only
    # a row that nets positive counts: a restore's own undo is never one of these.
    raised: list[RaisedStock] = []
    for row in rows:
        item = items.get(row.inventory_item_id)
        if row.product_master_id is None or not row.previous or item is None:
            continue
        previous_quantity = row.previous.get("current_quantity")
        if previous_quantity is None:
            continue
        after_undo = _active_amount(
            row.previous.get("status"), Decimal(str(previous_quantity))
        )
        before_undo = _active_amount(item.status, _left_on_item(row))
        delta = after_undo - before_undo
        if delta > 0:
            raised.append(
                RaisedStock(
                    product_id=row.product_master_id,
                    unit=str(row.unit),
                    amount=delta,
                )
            )
    since = rows[0].logged_at

    for row in rows:
        crud_inventory.apply_snapshot(
            items[row.inventory_item_id],
            row.previous,
        )
        await db.delete(row)
    await db.commit()

    restored = [
        await crud_inventory.get_inventory_item(db, item_id) for item_id in items
    ]
    return UndoResult(
        items=[item for item in restored if item is not None],
        raised=tuple(raised),
        since=since,
    )
