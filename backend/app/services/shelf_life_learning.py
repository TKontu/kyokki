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
    learned days   the median of the implied days of the 5 most recent observations (lower
                   median for an even count), each at least 1. One odd pack does not drag it.

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

from sqlalchemy import select
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
    """The shelf life one observation implies, never less than a day."""
    return max(1, (expiry_date - purchase_date).days)


def lower_median(values: Sequence[int]) -> int:
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


async def learn_shelf_life(
    db: AsyncSession, product_id: UUID
) -> LearnedShelfLife | None:
    """Set the product's shelf life to what the cook's recent dates imply. None: no change.

    Does not commit; the caller owns the transaction. The product row is locked, so two
    corrections of the same product learn one after the other rather than over each other.
    """
    await db.flush()
    product: Any = (
        await db.execute(
            select(ProductMaster)
            .where(ProductMaster.id == product_id)
            .with_for_update(of=ProductMaster)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if product is None:
        return None

    rows = (
        await db.execute(
            select(InventoryItem.purchase_date, InventoryItem.expiry_date)
            .where(InventoryItem.product_master_id == product_id)
            .where(InventoryItem.expiry_source == STATED)
            .where(InventoryItem.purchase_date.is_not(None))
            .where(InventoryItem.opened_date.is_(None))
            .where(InventoryItem.location != FREEZER)
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

    new_days = lower_median([implied_days(bought, expiry) for bought, expiry in rows])
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


async def learn_from_item(
    db: AsyncSession, item: InventoryItem
) -> list[MovedInventoryItem]:
    """Learn from one item if it is an observation. Returns the other items that moved."""
    if not is_observation(item):
        return []
    row: Any = item
    learned = await learn_shelf_life(db, row.product_master_id)
    if learned is None:
        return []
    return [moved for moved in learned.moved if moved.id != row.id]


async def update_item(
    db: AsyncSession, item_id: UUID, item_update: InventoryItemUpdate
) -> ItemUpdateResult:
    """`PATCH /inventory/{id}`: the correction, and what a date set by hand teaches.

    Learning runs inside the correction's transaction, only when the correction itself
    marked the date `manual` - a PATCH that names its own `expiry_source`, or changes
    nothing but other fields, teaches nothing.

    Raises:
        ItemFrozen: The item has been thrown away and this is not a restore.
    """
    moved: list[MovedInventoryItem] = []

    async def learn(item: InventoryItem) -> None:
        moved.extend(await learn_from_item(db, item))

    item = await crud_inventory.update_inventory_item(
        db, item_id, item_update, on_dated_by_hand=learn
    )
    return ItemUpdateResult(item=item, moved=moved)
