"""CRUD operations for InventoryItem model."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.consumption_log import ConsumptionAction, add_consumption_log
from app.crud.product_master import MovedInventoryItem
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.inventory_item import InventoryItemCreate, InventoryItemUpdate
from app.services.item_status import (
    DISCARDED,
    ItemEvent,
    ItemFrozen,
    is_frozen,
    next_status,
    opens_the_pack,
)
from app.services.units import quantise, to_canonical_decimal, unit_type_for

# Items in these states are gone from the kitchen and hidden from default listings.
INACTIVE_STATUSES = ("empty", "discarded")


#: What an event in the consumption log can change on an item, and so what undo puts back.
#: Location and the dates are here because the PATCH that corrects a quantity may move those
#: in the same request, and the undo reverses the request, not half of it.
SNAPSHOT_FIELDS = (
    "current_quantity",
    "initial_quantity",
    "status",
    "opened_date",
    "expiry_date",
    "expiry_source",
    "location",
    "consumed_at",
)


def snapshot(item: InventoryItem) -> dict[str, Any]:
    """The item's undoable fields as JSON, taken before an event changes them."""
    row: Any = item
    values: dict[str, Any] = {}
    for field in SNAPSHOT_FIELDS:
        value = getattr(row, field)
        if isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, date):  # datetime is a date too
            value = value.isoformat()
        values[field] = value
    return values


def apply_snapshot(item: InventoryItem, values: dict[str, Any]) -> None:
    """Put an item back the way `snapshot` found it."""
    row: Any = item
    row.current_quantity = Decimal(values["current_quantity"])
    row.initial_quantity = Decimal(values["initial_quantity"])
    row.status = values["status"]
    row.opened_date = _parse_date(values["opened_date"])
    row.expiry_date = _parse_date(values["expiry_date"])
    row.expiry_source = values["expiry_source"]
    row.location = values["location"]
    consumed_at = values["consumed_at"]
    row.consumed_at = datetime.fromisoformat(consumed_at) if consumed_at else None


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _track_consumed_at(row: Any, was: str, now: str) -> None:
    """Keep `consumed_at` saying when the item left the kitchen (H46).

    Stamped on the way out - finished or thrown away - and kept when an empty item is then
    discarded, because it was already gone. Cleared when it comes back: a restore, or a
    correction that finds some left after all.
    """
    if now in INACTIVE_STATUSES:
        if was not in INACTIVE_STATUSES or row.consumed_at is None:
            row.consumed_at = datetime.now(UTC)
    else:
        row.consumed_at = None


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
    consumed_since: datetime | None = None,
) -> list[InventoryItem]:
    """Get all inventory items with optional filters.

    Args:
        db: Database session.
        location: Optional location filter (main_fridge, freezer, pantry).
        status: Optional status filter (sealed, opened, partial, empty, discarded).
            An explicit status is always honoured, including inactive ones.
        expiring_days: Optional filter for items expiring within N days.
        include_inactive: Include empty and discarded items when no status is given.
        consumed_since: Also include items used up (``empty``) at or after this moment -
            the grey tiles an area's grid offers back (V4). Never discarded ones.

    Returns:
        List of inventory items matching the filters.
    """
    query = _with_product(select(InventoryItem))

    if location:
        query = query.where(InventoryItem.location == location)

    if status:
        query = query.where(InventoryItem.status == status)
    elif consumed_since is not None and not include_inactive:
        query = query.where(
            or_(
                InventoryItem.status.notin_(INACTIVE_STATUSES),
                and_(
                    InventoryItem.status == "empty",
                    InventoryItem.consumed_at >= consumed_since,
                ),
            )
        )
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

    The product's own figure wins over its category's (H52): bacon is meat but does not
    keep 180 days frozen. With neither, nothing happens at all - there is no useful
    answer for a frozen bottle of squash, and inventing one is worse than leaving the
    date alone.
    """
    product = item.product_master
    if product is None:
        return
    frozen_days = product.frozen_shelf_life_days
    if frozen_days is None and product.category_rel is not None:
        frozen_days = product.category_rel.frozen_shelf_life_days
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
    previous = snapshot(db_item)
    update_data = item_update.model_dump(exclude_unset=True)
    was = str(row.status)
    event = _event_for(was, update_data)

    before = Decimal(str(row.current_quantity))
    new_quantity = update_data.pop("current_quantity", None)
    if new_quantity is not None:
        # A correction (MVP-S4): raising above the full amount makes the new amount full, so
        # the quantity bar stays sensible
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

    # One row per PATCH, named after what it did. A discard or restore that also names an
    # amount logs that amount as the one thrown away or brought back; only a plain correction
    # is logged as `correct`, and only when the number actually moved - a new date or a new
    # shelf is not part of the quantity's history.
    if event is ItemEvent.DISCARD:
        add_consumption_log(
            db,
            item=db_item,
            action=ConsumptionAction.DISCARD,
            quantity=remaining,
            quantity_after=Decimal(0),
            previous=previous,
        )
    elif event is ItemEvent.RESTORE:
        add_consumption_log(
            db,
            item=db_item,
            action=ConsumptionAction.RESTORE,
            quantity=remaining,
            quantity_after=remaining,
            previous=previous,
        )
    elif remaining != before:
        add_consumption_log(
            db,
            item=db_item,
            action=ConsumptionAction.CORRECT,
            quantity=remaining - before,
            quantity_after=remaining,
            previous=previous,
        )
    _track_consumed_at(row, was, str(new_status))
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


@dataclass(frozen=True)
class BulkResult:
    """What a bulk move did, and to which rows, for the caller to broadcast."""

    changed: list[MovedInventoryItem]
    refused: int
    missing: int


async def move_many(
    db: AsyncSession, item_ids: Sequence[UUID], event: ItemEvent
) -> BulkResult:
    """Discard or restore several items in one transaction.

    Clearing a shelf of expired food through `PATCH` is one round trip, one transaction and
    one broadcast *per item* - thirteen of each for one tap - and a failure half way leaves
    the shelf half cleared with no way to tell. This is one transaction: all of it lands or
    none of it does.

    Every row still goes through H23's transition, so an item already in the bin is **refused**
    rather than discarded twice, and the log gets exactly one row per item that actually
    moved - none for an item that was already empty, since nothing was thrown away. `refused`
    and `missing` are counted rather than raised: a cook clearing thirteen things does not
    want the whole action to fail because one of them was already gone.
    """
    if not item_ids:
        return BulkResult(changed=[], refused=0, missing=0)

    query = (
        select(InventoryItem)
        .where(InventoryItem.id.in_(list(item_ids)))
        .with_for_update(of=InventoryItem)
    )
    found = list((await db.execute(query)).scalars().all())

    # One action, one step for undo: a cleared shelf comes back together
    batch_id = uuid4()
    changed: list[MovedInventoryItem] = []
    refused = 0
    for item in found:
        row: Any = item
        was = str(row.status)
        try:
            new_status = next_status(
                current=was,
                event=event,
                initial=Decimal(str(row.initial_quantity)),
                remaining=Decimal(str(row.current_quantity)),
                opened=row.opened_date is not None,
            )
        except ItemFrozen:
            refused += 1
            continue
        if new_status == was:
            refused += 1
            continue

        remaining = Decimal(str(row.current_quantity))
        add_consumption_log(
            db,
            item=item,
            previous=snapshot(item),
            batch_id=batch_id,
            action=ConsumptionAction.DISCARD
            if event is ItemEvent.DISCARD
            else ConsumptionAction.RESTORE,
            quantity=remaining,
            quantity_after=Decimal(0) if event is ItemEvent.DISCARD else remaining,
        )
        _track_consumed_at(row, was, str(new_status))
        row.status = new_status
        changed.append(
            MovedInventoryItem(
                id=row.id, current_quantity=row.current_quantity, status=new_status
            )
        )

    await db.commit()
    return BulkResult(
        changed=changed, refused=refused, missing=len(item_ids) - len(found)
    )


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

    apply_consumption(db, db_item, amount)

    await db.commit()
    return await _reload(db, db_item.id)


def apply_consumption(
    db: AsyncSession, db_item: InventoryItem, amount: Decimal
) -> None:
    """Take ``amount`` (already in the item's unit) off a locked item; does not commit.

    The per-item half of a consume: the status it moves to, the opened clock, `consumed_at`
    and the consumption log row, staged in the caller's transaction. The caller has locked
    the row and checked that ``amount`` is positive and no more than is there. Its product
    must be loaded, because opening a pack reads the product's opened shelf life.

    Raises:
        ItemFrozen: The item has been thrown away.
    """
    row: Any = db_item
    previous = snapshot(db_item)
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
    _track_consumed_at(row, str(row.status), str(new_status))
    row.current_quantity = new_quantity
    row.status = new_status

    add_consumption_log(
        db,
        item=db_item,
        action=ConsumptionAction.USE_FULL
        if new_quantity == 0
        else ConsumptionAction.USE_PARTIAL,
        quantity=amount,
        quantity_after=new_quantity,
        previous=previous,
    )


async def lock_active_items_for_product(
    db: AsyncSession, product_id: UUID, *, location: str | None = None
) -> list[InventoryItem]:
    """A product's items still in the kitchen, first to go first, locked for the transaction.

    The same order `get_inventory_items` lists them in - expiry, then `created_at`, then id -
    so a consume by name eats what the screen shows first. The product is loaded with each.
    """
    query = (
        _with_product(select(InventoryItem))
        .where(InventoryItem.product_master_id == product_id)
        .where(InventoryItem.status.notin_(INACTIVE_STATUSES))
    )
    if location:
        query = query.where(InventoryItem.location == location)
    query = (
        query.order_by(
            InventoryItem.expiry_date, InventoryItem.created_at, InventoryItem.id
        )
        .with_for_update(of=InventoryItem)
        .execution_options(populate_existing=True)
    )
    return list((await db.execute(query)).scalars().all())


async def lock_inventory_items(
    db: AsyncSession, item_ids: Sequence[UUID]
) -> dict[UUID, InventoryItem]:
    """Lock several items for the rest of the transaction, keyed by id."""
    query = (
        select(InventoryItem)
        .where(InventoryItem.id.in_(list(item_ids)))
        .with_for_update(of=InventoryItem)
        .execution_options(populate_existing=True)
    )
    found = (await db.execute(query)).scalars().all()
    return {cast(UUID, item.id): item for item in found}


async def _reload(db: AsyncSession, item_id: UUID) -> InventoryItem:
    """Re-read an item after commit with its product and category loaded."""
    item = await get_inventory_item(db, item_id)
    if item is None:  # pragma: no cover - the row was committed in this session
        raise LookupError(f"Inventory item {item_id} vanished after commit")
    return item
