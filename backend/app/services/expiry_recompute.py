"""When a product's shelf life changes, the food in the fridge changes with it (Q12).

Q11 gave the catalog two ways to change its mind about a shelf life - the product editor and
`POST /products/estimate` - and neither reached the food. `build_inventory_item` works out
`expiry_date` once, at confirm, and keeps no back-reference, so correcting mince from five days
to two left the mince in the fridge still claiming five. The sequence `HANDOFF.md` recommends -
confirm a receipt, then run the estimate - produced exactly that contradiction.

What may be recomputed is deliberately narrow, and the guards already existed:

    expiry_source == 'manual'      the cook typed this date      -> never touched
    expiry_source == 'scanned'     a barcode said so             -> never touched
    purchase_date is None          nothing to count from         -> skipped
    status empty / discarded       gone from the kitchen         -> skipped

It is the same shape as Q11's `shelf_life_source == 'cook'`: a value somebody chose outranks
one the system worked out.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.inventory_item import INACTIVE_STATUSES
from app.crud.product_master import MovedInventoryItem
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster

logger = get_logger(__name__)

# The one date a correction may overwrite. `manual` is the cook's, `scanned` is a barcode's.
RECOMPUTABLE_SOURCE = "calculated"


def sealed_expiry(product: ProductMaster, purchase_date: date) -> date:
    """What an unopened item of this product keeps until.

    The single home of `purchase_date + default_shelf_life_days`, which used to be written out
    in `generic_products.build_inventory_item` and again in `scanner_service`.
    """
    return purchase_date + timedelta(days=int(product.default_shelf_life_days))


def recomputed_expiry(item: InventoryItem, product: ProductMaster) -> date | None:
    """This item's expiry under the product's current shelf life, or None to leave it alone.

    An opened item is capped by Q5's opened clock, because **opening may only ever shorten**
    (`crud/inventory_item._start_opened_clock`). Without the cap, lengthening a product's shelf
    life would push an opened tub's date back out and undo the shortening that opening it
    earned - the one invariant `TestOpenedClock` pins.

    The cap copies that function's exemption too: loose produce is not a pack, so taking one
    apple from a bowl never started a clock and there is none to respect here.
    """
    row: Any = item
    if str(row.expiry_source) != RECOMPUTABLE_SOURCE:
        return None
    if row.purchase_date is None:
        return None

    expiry = sealed_expiry(product, row.purchase_date)

    opened_days = product.opened_shelf_life_days
    if (
        row.opened_date is not None
        and product.avg_piece_grams is None
        and opened_days is not None
    ):
        expiry = min(expiry, row.opened_date + timedelta(days=int(opened_days)))
    return expiry


async def recompute_expiry_for_product(
    db: AsyncSession, product: ProductMaster
) -> list[MovedInventoryItem]:
    """Bring this product's stock into line with its shelf life. Returns what moved.

    The return type is the plain one `product_merge` already uses - *"what a broadcast
    needs to know about an item"* - rather than live ORM rows, because that is all any
    caller does with it.

    Writes nothing to the session's transaction beyond the rows themselves - the caller
    commits, so a catalog refresh stays one transaction.

    The rows are locked for the duration. This is a read-modify-write over several rows, and
    consume does the same thing to one of them without a lock (H23), so the least this can do
    is not add a second unsynchronised writer.
    """
    query = (
        select(InventoryItem)
        .where(InventoryItem.product_master_id == product.id)
        .where(InventoryItem.status.notin_(INACTIVE_STATUSES))
        # `of` names the row to lock. It changes nothing today - nothing here joins another
        # table - but it keeps the lock from silently widening if one ever does, which is the
        # same reason `get_inventory_item` passes it (H23).
        .with_for_update(of=InventoryItem)
    )
    items = list((await db.execute(query)).scalars().all())

    moved: list[MovedInventoryItem] = []
    for item in items:
        row: Any = item
        expiry = recomputed_expiry(item, product)
        if expiry is None or expiry == row.expiry_date:
            continue
        row.expiry_date = expiry
        moved.append(
            MovedInventoryItem(
                id=row.id, current_quantity=row.current_quantity, status=row.status
            )
        )

    if moved:
        logger.info(
            "Expiry recomputed after a shelf-life change",
            extra={
                "product_id": str(product.id),
                "product": str(product.canonical_name),
                "considered": len(items),
                "moved": len(moved),
            },
        )
    return moved


async def recompute_expiry_for_products(
    db: AsyncSession, products: list[ProductMaster]
) -> list[MovedInventoryItem]:
    """The same, for a catalog refresh that changed many products at once."""
    moved: list[MovedInventoryItem] = []
    for product in products:
        moved.extend(await recompute_expiry_for_product(db, product))
    return moved
