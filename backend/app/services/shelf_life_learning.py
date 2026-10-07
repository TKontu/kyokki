"""A date the cook states teaches the product its shelf life (Q24).

The shelf-life estimate cannot read a printed date. Tortillas keep until November, a spread
until Christmas, cream six weeks, and the estimate said about a week for all of them. When the
cook corrected an item, that item kept the date, but the product learned nothing, so the next
pack arrived with the same wrong guess.

The cook's dates are already in the table, one per item, so there is nothing new to store.
What they imply is learned from the product's recent ones:

    observation    an item of this product whose date the cook stated (`manual`), counted
                   from its `purchase_date`, sealed (no `opened_date`) and not in the freezer
                   - opening and freezing both change the clock, so neither says anything
                   about how long a sealed pack keeps. Used-up and discarded items count.
                   A date on or before the purchase date ("eat today") is not one: it says
                   nothing about how long a sealed pack keeps, so it is ignored.
    learned days   with 1 or 2 observations, the most recent one (by `purchase_date`, then
                   `created_at`, then `id`), so a correction upwards is never held back by
                   an older row. With 3 or more, the median of the 5 most recent (the mean
                   of the two middle ones for an even count, rounded half up), so one odd
                   pack does not drag it.

A thawed item never teaches anything: a date the cook sets on an item whose clock is the
freezer's keeps `expiry_source = 'frozen'` (see `crud.inventory_item.update_inventory_item`),
so it is never an observation, and never re-dated either.

The learned number is stored exactly like one typed on the Products screen -
`default_shelf_life_days` with `shelf_life_source = 'cook'` (operator ruling, 2026-09-26) -
so no estimate overwrites it, and the product's other `calculated` stock moves with it.

Correcting the same item twice replaces its observation, because it is one row.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.crud.product_master import MovedInventoryItem
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.inventory_item import InventoryItemUpdate
from app.services.expiry_recompute import recompute_expiry_for_product

logger = get_logger(__name__)

#: How many of the cook's most recent dates are learned from.
RECENT_OBSERVATIONS = 5
#: From this many observations on, their median is learned rather than the newest one.
MEDIAN_FROM = 3
#: The one `expiry_source` that is the cook's own statement of a date.
STATED = "manual"
#: The source a learned shelf life is stored under: the cook's (operator ruling).
LEARNED_SOURCE = "cook"
FREEZER = "freezer"


@dataclass(frozen=True)
class LearnedShelfLife:
    """What a learning step changed, for the caller to broadcast and log."""

    product_id: UUID
    old_days: int
    new_days: int
    observations: int
    moved: list[MovedInventoryItem] = field(default_factory=list)


@dataclass(frozen=True)
class ItemUpdateResult:
    """A PATCH's item, plus the product's other items a learned shelf life moved."""

    item: InventoryItem | None
    moved: list[MovedInventoryItem] = field(default_factory=list)
    #: The product whose active stock this PATCH lowered (A4, F1) - a discard, or a
    #: quantity corrected down - as `crud.inventory_item.update_inventory_item` reported
    #: it back. None when nothing was lowered. The endpoint runs the auto-add check with
    #: it; this service does not call into `app.services.min_stock` itself.
    lowered_product_id: UUID | None = None
    #: The shelf life the product learned from this PATCH's date (CL7), so the cook can
    #: be told and every screen refreshed. None when nothing was learned or it did not
    #: change.
    learned: LearnedShelfLife | None = None


def is_observation(item: InventoryItem) -> bool:
    """Whether this item's date says how long a sealed pack of its product keeps."""
    row: Any = item
    return (
        str(row.expiry_source) == STATED
        and row.purchase_date is not None
        and row.opened_date is None
        and str(row.location) != FREEZER
    )


def implied_days(purchase_date: date, expiry_date: date) -> int:
    """The shelf life one observation implies."""
    return (expiry_date - purchase_date).days


def learned_days(most_recent_first: Sequence[int]) -> int:
    """What the observations teach, given newest first (see the module docstring)."""
    if len(most_recent_first) < MEDIAN_FROM:
        return most_recent_first[0]
    ordered = sorted(most_recent_first)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    # The mean of the middle two, rounded half up, in integers
    return (ordered[middle - 1] + ordered[middle] + 1) // 2


async def lock_product(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Lock the product row before anything else a date that may teach it will touch.

    The lock order is product, then items, everywhere: learning (and a catalog apply)
    locks the product and then every active item of it to re-date them. A PATCH that
    locked its own item first, or a quick add whose insert took a key-share lock on the
    product first, held what a concurrent sibling needed next, and one of the two was
    killed as a deadlock. Taking the product first makes the second caller simply wait.
    """
    product: ProductMaster | None = (
        await db.execute(
            select(ProductMaster)
            .where(ProductMaster.id == product_id)
            .with_for_update(of=ProductMaster)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    return product


def _observations(query: Select[Any], product_id: UUID) -> Select[Any]:
    """Narrow ``query`` to this product's observations (see the module docstring)."""
    return (
        query.where(InventoryItem.product_master_id == product_id)
        .where(InventoryItem.expiry_source == STATED)
        .where(InventoryItem.purchase_date.is_not(None))
        .where(InventoryItem.opened_date.is_(None))
        .where(InventoryItem.location != FREEZER)
        .where(InventoryItem.expiry_date > InventoryItem.purchase_date)
    )


async def count_observations(db: AsyncSession, product_id: UUID) -> int:
    """How many of the cook's dates this product could learn from (CL8: what a split
    leaves the source with). Counts them all, not only the recent ones learning reads."""
    total = await db.scalar(
        _observations(select(func.count()).select_from(InventoryItem), product_id)
    )
    return int(total or 0)


async def learn_shelf_life(
    db: AsyncSession, product_id: UUID
) -> LearnedShelfLife | None:
    """Set the product's shelf life to what the cook's recent dates imply. None: no change.

    Does not commit; the caller owns the transaction. The product row is locked, so two
    corrections of the same product learn one after the other rather than over each other.
    """
    await db.flush()
    product: Any = await lock_product(db, product_id)
    if product is None:
        return None

    rows = (
        await db.execute(
            _observations(
                select(InventoryItem.purchase_date, InventoryItem.expiry_date),
                product_id,
            )
            .order_by(
                InventoryItem.purchase_date.desc(),
                InventoryItem.created_at.desc(),
                InventoryItem.id.desc(),
            )
            .limit(RECENT_OBSERVATIONS)
        )
    ).all()
    if not rows:
        return None

    new_days = learned_days([implied_days(bought, expiry) for bought, expiry in rows])
    old_days = int(product.default_shelf_life_days)
    if new_days == old_days and str(product.shelf_life_source) == LEARNED_SOURCE:
        return None

    product.default_shelf_life_days = new_days
    product.shelf_life_source = LEARNED_SOURCE
    moved = await recompute_expiry_for_product(db, product)

    logger.info(
        "Shelf life learned from the cook's dates",
        extra={
            "product_id": str(product_id),
            "old_days": old_days,
            "new_days": new_days,
            "observations": len(rows),
            "moved": len(moved),
        },
    )
    return LearnedShelfLife(
        product_id=product_id,
        old_days=old_days,
        new_days=new_days,
        observations=len(rows),
        moved=moved,
    )


async def learn_from_item_reporting(
    db: AsyncSession, item: InventoryItem
) -> tuple[LearnedShelfLife | None, list[MovedInventoryItem]]:
    """Learn from one item if it is an observation: what was learned, and what moved.

    The learned shelf life is None when nothing changed (not an observation, or the same
    answer again); the list is the product's other items that moved with it.
    """
    if not is_observation(item):
        return None, []
    row: Any = item
    learned = await learn_shelf_life(db, row.product_master_id)
    if learned is None:
        return None, []
    return learned, [moved for moved in learned.moved if moved.id != row.id]


async def learn_from_item(
    db: AsyncSession, item: InventoryItem
) -> list[MovedInventoryItem]:
    """Learn from one item if it is an observation. Returns the other items that moved."""
    _, moved = await learn_from_item_reporting(db, item)
    return moved


async def update_item(
    db: AsyncSession, item_id: UUID, item_update: InventoryItemUpdate
) -> ItemUpdateResult:
    """`PATCH /inventory/{id}`: the correction, and what a date set by hand teaches.

    Learning runs inside the correction's transaction, only when the correction itself
    marked the date `manual` - a PATCH that names its own `expiry_source`, or changes
    nothing but other fields, teaches nothing. A PATCH that sends a date locks the product
    before the item, the order learning needs (`lock_product`).

    Raises:
        ItemFrozen: The item has been thrown away and this is not a restore.
    """
    moved: list[MovedInventoryItem] = []
    if "expiry_date" in item_update.model_fields_set:
        # A new date may teach the product, so its row is locked before the item's
        # (see `lock_product`). Read without a lock: an item changes product only through
        # a split or its undo (`services.product_split`, CL8), which re-learns both
        # products itself, so one landing in between leaves nothing unlearned.
        product_id = (
            await db.execute(
                select(InventoryItem.product_master_id).where(
                    InventoryItem.id == item_id
                )
            )
        ).scalar_one_or_none()
        if product_id is not None:
            await lock_product(db, product_id)

    learned: list[LearnedShelfLife] = []

    async def learn(item: InventoryItem) -> None:
        taught, others = await learn_from_item_reporting(db, item)
        moved.extend(others)
        if taught is not None:
            learned.append(taught)

    item, lowered_product_id = await crud_inventory.update_inventory_item(
        db, item_id, item_update, on_dated_by_hand=learn
    )
    return ItemUpdateResult(
        item=item,
        moved=moved,
        lowered_product_id=lowered_product_id,
        learned=learned[-1] if learned else None,
    )
