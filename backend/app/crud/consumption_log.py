"""CRUD operations for ConsumptionLog model."""

from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem

ConsumptionAction = Literal["use_partial", "use_full", "discard", "adjust"]


def add_consumption_log(
    db: AsyncSession,
    *,
    item: InventoryItem,
    action: ConsumptionAction,
    quantity: Decimal,
) -> ConsumptionLog:
    """Stage a consumption log row in the caller's transaction.

    Does not flush or commit, so the row lands atomically with the inventory change
    that caused it.
    """
    log = ConsumptionLog(
        inventory_item_id=item.id,
        product_master_id=item.product_master_id,
        action=action,
        quantity_consumed=quantity,
    )
    db.add(log)
    return log
