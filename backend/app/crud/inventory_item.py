"""CRUD operations for InventoryItem model."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.inventory_item import InventoryItem
from app.schemas.inventory_item import InventoryItemCreate, InventoryItemUpdate


async def get_inventory_items(
    db: AsyncSession,
    location: str | None = None,
    status: str | None = None,
    expiring_days: int | None = None,
) -> list[InventoryItem]:
    """Get all inventory items with optional filters.

    Args:
        db: Database session.
        location: Optional location filter (main_fridge, freezer, pantry).
        status: Optional status filter (sealed, opened, partial, empty, discarded).
        expiring_days: Optional filter for items expiring within N days.

    Returns:
        List of inventory items matching the filters.
    """
    query = select(InventoryItem)

    if location:
        query = query.where(InventoryItem.location == location)

    if status:
        query = query.where(InventoryItem.status == status)

    if expiring_days is not None:
        expiry_threshold = date.today() + timedelta(days=expiring_days)
        query = query.where(InventoryItem.expiry_date <= expiry_threshold)

    query = query.order_by(InventoryItem.expiry_date)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_inventory_item(
    db: AsyncSession, item_id: UUID
) -> InventoryItem | None:
    """Get an inventory item by ID.

    Args:
        db: Database session.
        item_id: Inventory item UUID.

    Returns:
        Inventory item if found, None otherwise.
    """
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id)
    )
    return result.scalar_one_or_none()


async def create_inventory_item(
    db: AsyncSession, item: InventoryItemCreate
) -> InventoryItem:
    """Create a new inventory item.

    Args:
        db: Database session.
        item: Inventory item data.

    Returns:
        Created inventory item.

    Raises:
        IntegrityError: If foreign key constraint fails (invalid product_master_id).
    """
    db_item = InventoryItem(**item.model_dump())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item


async def update_inventory_item(
    db: AsyncSession, item_id: UUID, item_update: InventoryItemUpdate
) -> InventoryItem | None:
    """Update an inventory item.

    Args:
        db: Database session.
        item_id: Inventory item UUID.
        item_update: Fields to update.

    Returns:
        Updated inventory item if found, None otherwise.
    """
    db_item = await get_inventory_item(db, item_id)
    if not db_item:
        return None

    # Update only provided fields
    update_data = item_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_item, field, value)

    await db.commit()
    await db.refresh(db_item)
    return db_item


async def delete_inventory_item(db: AsyncSession, item_id: UUID) -> bool:
    """Delete an inventory item.

    Args:
        db: Database session.
        item_id: Inventory item UUID.

    Returns:
        True if deleted, False if not found.
    """
    db_item = await get_inventory_item(db, item_id)
    if not db_item:
        return False

    await db.delete(db_item)
    await db.commit()
    return True


async def consume_inventory_item(
    db: AsyncSession, item_id: UUID, quantity: Decimal
) -> InventoryItem | None:
    """Consume/reduce quantity from an inventory item.

    Args:
        db: Database session.
        item_id: Inventory item UUID.
        quantity: Amount to consume.

    Returns:
        Updated inventory item if found, None otherwise.

    Raises:
        ValueError: If trying to consume more than available quantity.
    """
    db_item = await get_inventory_item(db, item_id)
    if not db_item:
        return None

    if quantity > db_item.current_quantity:
        raise ValueError(
            f"Cannot consume {quantity} - only {db_item.current_quantity} available"
        )

    # Calculate new quantity
    new_quantity = db_item.current_quantity - quantity
    db_item.current_quantity = new_quantity

    # Update status based on quantity
    if new_quantity == 0:
        db_item.status = "empty"
    elif new_quantity < db_item.initial_quantity:
        # If item was sealed and we're consuming from it, mark as opened and set date
        if db_item.status == "sealed":
            db_item.opened_date = date.today()

        # Determine if partial or just opened based on remaining percentage
        remaining_percentage = (new_quantity / db_item.initial_quantity) * 100
        if remaining_percentage < 75:  # Less than 75% remaining
            db_item.status = "partial"
        else:
            db_item.status = "opened"

    await db.commit()
    await db.refresh(db_item)
    return db_item
