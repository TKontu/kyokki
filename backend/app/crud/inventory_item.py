"""CRUD operations for InventoryItem model."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.consumption_log import ConsumptionAction, add_consumption_log
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.inventory_item import InventoryItemCreate, InventoryItemUpdate
from app.services.item_status import (
    DISCARDED,
    ItemEvent,
    is_frozen,
    next_status,
    opens_the_pack,
)
from app.services.units import quantise, to_canonical_decimal, unit_type_for

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


async def get_inventory_item(
    db: AsyncSession, item_id: UUID, *, for_update: bool = False
) -> InventoryItem | None:
    """Get an inventory item by ID.

    Args:
        db: Database session.
        item_id: Inventory item UUID.
        for_update: Lock the row until the transaction ends. Every writer passes this: consume
            and correction are read-modify-write, so two callers without it both read 4 and both
            write 3, losing one change while both log rows land (H23).

    Returns:
        Inventory item if found, None otherwise.
    """
    query = (
        _with_product(select(InventoryItem))
        .where(InventoryItem.id == item_id)
        .execution_options(populate_existing=True)
    )
    if for_update:
        # `of` names the row to lock: `_with_product` uses `selectinload`, which issues its own
        # SELECT, so the outer statement would lock only this table anyway - but it would not if
        # anyone swapped in a `joinedload`, and a lock that quietly widens is worse than one that
        # is explicit.
        query = query.with_for_update(of=InventoryItem)
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


def _start_opened_clock(item: InventoryItem) -> None:
    """Shorten the expiry once a pack is opened (Q5).

    An opened tub of cream should stop claiming the fortnight it had sealed. Opening can only
    ever bring the date forward - a jar opened the day before its printed date does not gain a
    fortnight - so the earlier of the two wins.

    **Loose produce is not a pack.** Taking one apple out of a bowl of thirteen does not open
    anything, and shortening the other twelve would be plainly wrong. The tell is the piece
    weight: we only record one for things sold loose and counted out. A milk carton is stored
    as a single piece too, so counting in pieces is *not* the test - it would wrongly exempt
    every carton and jar.
    """
    row: Any = item
    product = item.product_master
    if product is not None and product.avg_piece_grams is not None:
        return
    opened_days = product.opened_shelf_life_days if product is not None else None
    if opened_days is None:
        return
    opened_expiry = row.opened_date + timedelta(days=int(opened_days))
    if opened_expiry < row.expiry_date:
        row.expiry_date = opened_expiry


def _start_frozen_clock(item: InventoryItem, update_data: dict[str, Any]) -> None:
    """Re-date an item that is going into the freezer (Q12, DEC-10).

    Counted from today rather than from `purchase_date`, because what matters is when it
    went in: mince frozen on the day it was bought and mince frozen on its last good day
    both keep about as long from that moment.

    `frozen` rather than `calculated` so the date survives what comes next: a later
    shelf-life correction re-dates `calculated` stock (Q12's other half), and thawing the
    clock again every time the catalog learned something would undo this immediately.

    A category with no frozen figure does nothing at all - there is no useful answer for a
    frozen bottle of squash, and inventing one is worse than leaving the date alone.
    """
    product = item.product_master
    category = product.category_rel if product is not None else None
    frozen_days = category.frozen_shelf_life_days if category is not None else None
    if frozen_days is None:
        return
    update_data["expiry_date"] = date.today() + timedelta(days=int(frozen_days))
    update_data["expiry_source"] = "frozen"


def _event_for(current: str, update_data: dict[str, Any]) -> ItemEvent:
    """Which of the four things a PATCH is actually doing (H23).

    The client says what it wants the item to *be*; the table needs to know what *happened*.
    Only `status` carries that: "Mark as gone" sends `discarded` alone, and asking for an
    active status on a thrown-away item is the way back. Everything else - a quantity, a date,
    a location - is a correction.
    """
    wanted = update_data.get("status")
    if wanted == DISCARDED:
        return ItemEvent.DISCARD
    if wanted is not None and is_frozen(current):
        return ItemEvent.RESTORE
    return ItemEvent.CORRECT


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

    Raises:
        ItemFrozen: The item has been thrown away and this is not a restore.
    """
    # Locked for the same reason consume is: every decision below - the discard dedupe, the
    # above-full test, the manual-expiry test, the freezer test - is made against this read,
    # and two concurrent PATCHes used to make all four of them twice (H23).
    db_item = await get_inventory_item(db, item_id, for_update=True)
    if not db_item:
        return None

    row: Any = db_item
    update_data = item_update.model_dump(exclude_unset=True)
    was = str(row.status)
    event = _event_for(was, update_data)

    new_quantity = update_data.pop("current_quantity", None)
    if new_quantity is not None:
        # A correction (MVP-S4): not logged as consumption; raising above the full amount
        # makes the new amount full, so the quantity bar stays sensible
        if new_quantity > row.initial_quantity:
            row.initial_quantity = new_quantity
        row.current_quantity = new_quantity

    remaining = Decimal(str(row.current_quantity))
    # The status is derived even when the client named one: a PATCH used to be able to set any
    # status over any other, `discarded -> sealed` included, by suppressing the rules entirely.
    new_status = next_status(
        current=was,
        event=event,
        initial=Decimal(str(row.initial_quantity)),
        remaining=remaining,
        opened=row.opened_date is not None,
    )
    update_data.pop("status", None)

    if event is ItemEvent.DISCARD:
        add_consumption_log(
            db, item=db_item, action=ConsumptionAction.DISCARD, quantity=remaining
        )
    if opens_the_pack(was, new_status):
        row.opened_date = date.today()
        _start_opened_clock(db_item)
    row.status = new_status

    if (
        "expiry_date" in update_data
        and "expiry_source" not in update_data
        and update_data["expiry_date"] != row.expiry_date
    ):
        # A date set by hand, so the badge no longer claims it was calculated
        update_data["expiry_source"] = "manual"
    elif (
        update_data.get("location") == "freezer"
        and row.location != "freezer"
        and "expiry_date" not in update_data
    ):
        # Putting it in the freezer restarts the clock on a longer one (Q12, DEC-10). Only
        # when the cook did not also name a date: theirs wins, as it does everywhere else.
        _start_frozen_clock(db_item, update_data)

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


def _amount_in_item_units(
    quantity: Decimal, unit: str | None, item_unit: str
) -> Decimal:
    """`quantity` expressed in the unit the item is stored in (H23).

    Omitting the unit means "the item's own", which is what the iPad does. Naming one is for
    callers that cannot see the item: converting 0.2 l into 2 dl is helpful, subtracting 200 g
    from a count of twelve apples is not, so a different kind of measure is refused.
    """
    if unit is None:
        return quantise(quantity)
    if unit_type_for(unit) != unit_type_for(item_unit):
        raise ValueError(f"Cannot consume {unit} from an item measured in {item_unit}")
    converted = to_canonical_decimal(quantity, unit)
    return quantise(converted if converted is not None else quantity)


async def consume_inventory_item(
    db: AsyncSession, item_id: UUID, quantity: Decimal, unit: str | None = None
) -> InventoryItem | None:
    """Consume/reduce quantity from an inventory item.

    Args:
        db: Database session.
        item_id: Inventory item UUID.
        quantity: Amount to consume.

    Returns:
        Updated inventory item if found, None otherwise.

    Raises:
        ValueError: If the amount is not consumable - more than is there, or so small it
            rounds away to nothing.
        ItemFrozen: The item has been thrown away.
    """
    # Locked: two taps on Consume used to both read 4, both pass the check below, and both
    # write 3 - one helping vanished while both log rows landed, so the count and the history
    # disagreed (H23, `docs/reviews/pipeline-foundations.md`).
    db_item = await get_inventory_item(db, item_id, for_update=True)
    if not db_item:
        return None

    row: Any = db_item
    amount = _amount_in_item_units(quantity, unit, str(row.unit))
    if amount <= 0:
        # Rounding is what makes this reachable: a third of 0.01 dl is not a helping, and
        # logging it as one would say something happened that did not.
        raise ValueError(f"Cannot consume {quantity} - it rounds to nothing")
    if amount > row.current_quantity:
        raise ValueError(
            f"Cannot consume {quantity} - only {row.current_quantity} available"
        )

    new_quantity = quantise(row.current_quantity - amount)
    # Raises ItemFrozen for a discarded item, which is the point: it is not in the kitchen.
    new_status = next_status(
        current=str(row.status),
        event=ItemEvent.CONSUME,
        initial=Decimal(str(row.initial_quantity)),
        remaining=new_quantity,
        opened=row.opened_date is not None,
    )

    if opens_the_pack(str(row.status), new_status):
        row.opened_date = date.today()
        _start_opened_clock(db_item)
    row.current_quantity = new_quantity
    row.status = new_status

    add_consumption_log(
        db,
        item=db_item,
        action=ConsumptionAction.USE_FULL
        if new_quantity == 0
        else ConsumptionAction.USE_PARTIAL,
        quantity=amount,
    )

    await db.commit()
    return await _reload(db, db_item.id)


async def _reload(db: AsyncSession, item_id: UUID) -> InventoryItem:
    """Re-read an item after commit with its product and category loaded."""
    item = await get_inventory_item(db, item_id)
    if item is None:  # pragma: no cover - the row was committed in this session
        raise LookupError(f"Inventory item {item_id} vanished after commit")
    return item
