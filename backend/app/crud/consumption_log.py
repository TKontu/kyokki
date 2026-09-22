"""CRUD operations for ConsumptionLog model."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.schemas.consumption_log import ConsumptionAction

__all__ = [
    "ConsumptionAction",
    "add_consumption_log",
    "list_consumption_logs",
    "newest_batch",
]


def add_consumption_log(
    db: AsyncSession,
    *,
    item: InventoryItem,
    action: ConsumptionAction,
    quantity: Decimal,
    quantity_after: Decimal,
    previous: dict[str, Any],
    batch_id: UUID | None = None,
) -> ConsumptionLog | None:
    """Stage a consumption log row in the caller's transaction.

    Does not flush or commit, so the row lands atomically with the inventory change
    that caused it.

    An event that moved nothing writes nothing (H46): clearing an item that was already empty
    is not waste, and restoring it brings nothing back. Returns the row, or None when none was
    written.

    `previous` is the item as it was before the event, for undo to put back. Rows written by
    one action share a `batch_id`, so they are undone together; a lone event gets its own.
    """
    if quantity == 0:
        return None
    log = ConsumptionLog(
        inventory_item_id=item.id,
        product_master_id=item.product_master_id,
        action=action,
        quantity_consumed=abs(quantity),
        quantity_after=quantity_after,
        batch_id=batch_id or uuid4(),
        previous=previous,
    )
    db.add(log)
    return log


async def list_consumption_logs(
    db: AsyncSession,
    *,
    actions: Sequence[ConsumptionAction] | None = None,
    product_master_id: UUID | None = None,
    inventory_item_id: UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[ConsumptionLog]:
    """Read the history back, newest first (H46).

    Args:
        db: Database session.
        actions: Only these kinds of event; ``None`` or empty means all of them.
        product_master_id: Only this product's events, across all its items.
        inventory_item_id: Only this item's events.
        since: Only events logged at or after this moment.
        until: Only events logged before this moment.
        limit: Page size; ``None`` returns every match.
        offset: How many of the newest events to skip.

    Returns:
        Log rows with their item and product loaded, for `product_name` and `unit`.
    """
    query = select(ConsumptionLog).options(
        selectinload(ConsumptionLog.inventory_item),
        selectinload(ConsumptionLog.product_master),
    )

    if actions:
        query = query.where(ConsumptionLog.action.in_(list(actions)))
    if product_master_id is not None:
        query = query.where(ConsumptionLog.product_master_id == product_master_id)
    if inventory_item_id is not None:
        query = query.where(ConsumptionLog.inventory_item_id == inventory_item_id)
    if since is not None:
        query = query.where(ConsumptionLog.logged_at >= since)
    if until is not None:
        query = query.where(ConsumptionLog.logged_at < until)

    # Total order so a page boundary cannot split or repeat rows logged in the same instant
    query = query.order_by(ConsumptionLog.logged_at.desc(), ConsumptionLog.id.desc())

    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def newest_batch(db: AsyncSession) -> list[ConsumptionLog]:
    """The rows of the most recent action, with their item and product loaded.

    The most recent action is the batch of the newest row. Empty when nothing has been logged.
    """
    newest = await db.execute(
        select(ConsumptionLog.batch_id)
        .order_by(ConsumptionLog.logged_at.desc(), ConsumptionLog.id.desc())
        .limit(1)
    )
    batch_id = newest.scalar_one_or_none()
    if batch_id is None:
        return []
    result = await db.execute(
        select(ConsumptionLog)
        .where(ConsumptionLog.batch_id == batch_id)
        .options(
            selectinload(ConsumptionLog.inventory_item),
            selectinload(ConsumptionLog.product_master),
        )
        .order_by(ConsumptionLog.logged_at, ConsumptionLog.id)
        # A fresh read every time: undo re-reads under its locks and must see another
        # request's commit rather than this session's cached rows
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())
