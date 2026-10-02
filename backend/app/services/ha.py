"""Shapes and logic for Home Assistant's REST endpoints (docs/HOME_ASSISTANT_SPEC.md).

Thin over what already exists: stock by name (`services.stock`), low stock (AG6's
`services.shopping_generate`), and the shared "expired" rule
(`crud.inventory_item.get_inventory_items(expiring_days=...)`, the same one the iPad's
expired shelf and the agent API use). This module only shapes their results into HA's JSON;
it does not restate any of their logic.
"""

from collections import Counter
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import inventory_item as crud_inventory
from app.models.product_master import ProductMaster
from app.schemas.ha import (
    HaConsumedItem,
    HaConsumeResponse,
    HaExpiringItem,
    HaExpiringResponse,
    HaLowStockItem,
    HaLowStockResponse,
    HaStatusResponse,
)
from app.schemas.shopping_list_item import (
    ShoppingListItemCreate,
    ShoppingPriority,
    ShoppingSource,
)
from app.schemas.stock import StockConsumeRequest, StockConsumeResponse
from app.services import shopping_generate
from app.services import stock as stock_service

#: Same window `stock.py` calls "expiring" (`EXPIRING_WITHIN_DAYS`).
EXPIRING_WITHIN_DAYS = 3
#: `expiring_days=-1`: the earliest expiry is strictly before today - the iPad's expired
#: shelf and the agent API's rule, not restated here.
EXPIRED_DAYS = -1


def _percent(part: Decimal, whole: Decimal) -> int:
    """`part` as a percentage of `whole`, 0 when `whole` is not positive."""
    if whole <= 0:
        return 0
    return int((part / whole * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def status(db: AsyncSession) -> HaStatusResponse:
    """Inventory counts for HA's REST sensor platform (one call, several sensors).

    F1: `expiring_within_3_days` and `expired` are disjoint - an already-expired item is
    `expired` only, not also counted as "expiring". `expiring_soon` (`expiring_days=3`)
    has no lower bound, so it is every expired item plus every item due in the next 3
    days; subtracting the (already fetched) expired count leaves just the latter, without
    restating the crud layer's date arithmetic.
    """
    active = await crud_inventory.get_inventory_items(db)
    expiring_soon = await crud_inventory.get_inventory_items(
        db, expiring_days=EXPIRING_WITHIN_DAYS
    )
    expired = await crud_inventory.get_inventory_items(db, expiring_days=EXPIRED_DAYS)
    by_location: Counter[str] = Counter(str(item.location) for item in active)
    return HaStatusResponse(
        total_items=len(active),
        expiring_within_3_days=len(expiring_soon) - len(expired),
        expired=len(expired),
        by_location=dict(by_location),
        last_updated=datetime.now(UTC),
    )


async def expiring(
    db: AsyncSession, *, days: int = 3, limit: int = 10
) -> HaExpiringResponse:
    """Items expiring within `days`, soonest first, truncated to `limit`.

    F1: each item carries `expired` (the same `expiry_date < today` rule `status` uses),
    so a dashboard or voice intent can tell an already-expired item from one still coming.
    """
    # Any: the models declare untyped `Column`s, which mypy reads as Column[...], not values.
    items: list[Any] = await crud_inventory.get_inventory_items(db, expiring_days=days)
    today = date.today()
    shaped = [
        HaExpiringItem(
            id=item.id,
            name=item.product_name,
            category=item.category,
            expiry_date=item.expiry_date,
            days_until_expiry=(item.expiry_date - today).days,
            quantity_percent=_percent(
                Decimal(item.current_quantity), Decimal(item.initial_quantity)
            ),
            expired=item.expiry_date < today,
        )
        for item in items[:limit]
    ]
    return HaExpiringResponse(items=shaped, count=len(shaped))


async def _categories_for(db: AsyncSession, product_ids: set[UUID]) -> dict[UUID, str]:
    if not product_ids:
        return {}
    rows = await db.execute(
        select(ProductMaster.id, ProductMaster.category).where(
            ProductMaster.id.in_(product_ids)
        )
    )
    return {product_id: category for product_id, category in rows.all()}


async def low_stock(db: AsyncSession) -> HaLowStockResponse:
    """Products below their restock point, for shopping reminders. Writes nothing.

    A dry run of AG6's `low_stock` source: every line it would add, raise or leave alone
    is a product currently short, whether or not the open list already has it.
    """
    result = await shopping_generate.generate(db, ["low_stock"], dry_run=True)
    lines = [*result.added, *result.updated, *result.unchanged]
    categories = await _categories_for(db, {line.product_id for line in lines})
    shaped = [
        HaLowStockItem(
            id=line.product_id,
            name=line.name,
            category=categories.get(line.product_id, "unknown"),
            quantity_percent=_percent(
                Decimal(line.on_hand or 0), Decimal(line.min_stock)
            ),
            on_shopping_list=line.item_id is not None,
        )
        for line in lines
    ]
    return HaLowStockResponse(items=shaped, count=len(shaped))


async def consume_by_name(
    db: AsyncSession, name: str, amount: Decimal, unit: str
) -> tuple[HaConsumeResponse, StockConsumeResponse]:
    """Consume by name and amount, shaped for HA, and the raw result to broadcast from.

    Does not commit the idempotency claim itself - the caller remembers the shaped
    response, not this function's `StockConsumeResponse`.

    Raises:
        ProductNotFound, AmbiguousProduct: `services.product_lookup`'s own errors.
        stock_service.InsufficientStock, stock_service.InvalidConsume: as `stock.consume`.
    """
    request = StockConsumeRequest(
        product=name,
        amount=amount,
        unit=unit,
        location=None,
        dry_run=False,
        allow_partial=False,
    )
    result = await stock_service.consume(db, request)
    consumed_amount = sum((c.amount for c in result.consumed), Decimal(0))
    before = result.remaining_total + consumed_amount
    response = HaConsumeResponse(
        item=HaConsumedItem(
            name=result.product_name,
            quantity_before=before,
            quantity_after=result.remaining_total,
        )
    )
    return response, result


def shopping_add_item(
    name: str,
    amount: Decimal,
    unit: str,
    priority: ShoppingPriority = ShoppingPriority.NORMAL,
) -> ShoppingListItemCreate:
    """What `POST /api/ha/shopping/add` puts on the list: a free-text line by name."""
    return ShoppingListItemCreate(
        product_master_id=None,
        name=name,
        quantity=amount,
        unit=unit,
        priority=priority,
        source=ShoppingSource.MANUAL,
    )
