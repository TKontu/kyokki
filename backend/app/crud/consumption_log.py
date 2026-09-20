"""CRUD operations for ConsumptionLog model."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.schemas.consumption_log import ConsumptionAction

__all__ = ["ConsumptionAction", "add_consumption_log"]


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
