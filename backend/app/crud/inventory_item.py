"""CRUD operations for InventoryItem model."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.consumption_log import add_consumption_log
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.inventory_item import InventoryItemCreate, InventoryItemUpdate

# Items in these states are gone from the kitchen and hidden from default listings.
INACTIVE_STATUSES = ("empty", "discarded")


def _with_product(
    query: Select[tuple[InventoryItem]],
) -> Select[tuple[InventoryItem]]:
    """Eager-load the product and its category for response serialisation."""
    return query.options(
        selectinload(InventoryItem.product_master).selectinload(
            ProductMaster.category_rel
        )
    )


async def get_inventory_items(
    db: AsyncSession,
    location: str | None = None,
    status: str | None = None,
    expiring_days: int | None = None,
    include_inactive: bool = False,
) -> list[InventoryItem]:
    """Get all inventory items with optional filters.

    Args:
        db: Database session.
        location: Optional location filter (main_fridge, freezer, pantry).
        status: Optional status filter (sealed, opened, partial, empty, discarded).
            An explicit status is always honoured, including inactive ones.
        expiring_days: Optional filter for items expiring within N days.
        include_inactive: Include empty and discarded items when no status is given.

    Returns:
        List of inventory items matching the filters.
    """
    query = _with_product(select(InventoryItem))

    if location:
        query = query.where(InventoryItem.location == location)

    if status:
        query = query.where(InventoryItem.status == status)
    elif not include_inactive:
        query = query.where(InventoryItem.status.notin_(INACTIVE_STATUSES))

    if expiring_days is not None:
        expiry_threshold = date.today() + timedelta(days=expiring_days)
        query = query.where(InventoryItem.expiry_date <= expiry_threshold)

    # Total order so equal-expiry items keep their place between refetches
    query = query.order_by(
        InventoryItem.expiry_date, InventoryItem.created_at, InventoryItem.id
    )

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_inventory_item(db: AsyncSession, item_id: UUID) -> InventoryItem | None:
    """Get an inventory item by ID.

    Args:
        db: Database session.
        item_id: Inventory item UUID.

    Returns:
        Inventory item if found, None otherwise.
    """
    query = (
        _with_product(select(InventoryItem))
        .where(InventoryItem.id == item_id)
        .execution_options(populate_existing=True)
    )
    result = await db.execute(query)
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
    return await _reload(db, db_item.id)


def apply_quantity_status(item: InventoryItem, new_quantity: Decimal) -> None:
    """Status after the remaining quantity changes, for consume and for corrections.

    0 is empty; below the full amount an item is opened (75 % or more left) or partial, and a
    sealed item gets its opened date. An empty item brought back to full counts as opened.
    """
    row: Any = item  # Column-typed model: compare and assign plain values
    if new_quantity == 0:
        row.status = "empty"
    elif new_quantity < row.initial_quantity:
        if row.status == "sealed":
            row.opened_date = date.today()
        remaining_percentage = (new_quantity / row.initial_quantity) * 100
        row.status = "partial" if remaining_percentage < 75 else "opened"
    elif row.status == "empty":
        row.status = "opened"


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

    if update_data.get("status") == "discarded" and db_item.status != "discarded":
        add_consumption_log(
            db, item=db_item, action="discard", quantity=db_item.current_quantity
        )

    row: Any = db_item
    new_quantity = update_data.pop("current_quantity", None)
    if new_quantity is not None:
        # A correction (MVP-S4): not logged as consumption; raising above the full amount
        # makes the new amount full, so the quantity bar stays sensible
        if new_quantity > row.initial_quantity:
            row.initial_quantity = new_quantity
        row.current_quantity = new_quantity
        if "status" not in update_data:
            apply_quantity_status(db_item, new_quantity)

    if (
        "expiry_date" in update_data
        and "expiry_source" not in update_data
        and update_data["expiry_date"] != row.expiry_date
    ):
        # A date set by hand, so the badge no longer claims it was calculated
        update_data["expiry_source"] = "manual"

    for field, value in update_data.items():
        setattr(db_item, field, value)

    await db.commit()
    return await _reload(db, db_item.id)


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


async def get_active_items_by_product(
    db: AsyncSession, product_id: UUID
) -> list[InventoryItem]:
    """Get non-empty, non-discarded inventory items for a product, oldest expiry first.

    Args:
        db: Database session.
        product_id: Product master UUID.

    Returns:
        List of active inventory items ordered by expiry date ascending.
    """
    query = (
        select(InventoryItem)
        .where(InventoryItem.product_master_id == product_id)
        .where(InventoryItem.status.notin_(INACTIVE_STATUSES))
        .order_by(
            InventoryItem.expiry_date.asc(),
            InventoryItem.created_at.asc(),
            InventoryItem.id.asc(),
        )
    )
    result = await db.execute(query)
    return list(result.scalars().all())


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

    add_consumption_log(
        db,
        item=db_item,
        action="use_full" if new_quantity == 0 else "use_partial",
        quantity=quantity,
    )

    apply_quantity_status(db_item, new_quantity)

    await db.commit()
    return await _reload(db, db_item.id)


async def _reload(db: AsyncSession, item_id: UUID) -> InventoryItem:
    """Re-read an item after commit with its product and category loaded."""
    item = await get_inventory_item(db, item_id)
    if item is None:  # pragma: no cover - the row was committed in this session
        raise LookupError(f"Inventory item {item_id} vanished after commit")
    return item
