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

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
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


def _left_on_item(row: Any) -> Decimal:
    """The quantity the event left on the item row itself.

    Usually `quantity_after`. A discard is the exception: nothing is left in the kitchen, so
    the log says 0, but the item keeps its quantity frozen (H23) - that is the amount thrown
    away, and what a restore brings back.
    """
    if row.action == ConsumptionAction.DISCARD:
        return Decimal(str(row.quantity_consumed))
    return Decimal(str(row.quantity_after))


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
        )
        for row in rows
    ]
    return rows[0].batch_id, rows[-1].logged_at, steps


async def undo(db: AsyncSession, batch_id: UUID) -> list[InventoryItem]:
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
    return [item for item in restored if item is not None]
