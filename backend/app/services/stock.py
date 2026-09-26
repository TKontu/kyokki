"""Stock as an agent sees it: per product, added by name, consumed by name (AG2).

Thin on purpose. Adding is quick add; consuming applies the single-item consume's rules
(`crud.inventory_item.apply_consumption`) to each item in turn, first to expire first, in
one transaction. The iPad's item-by-item routes are untouched.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.crud.inventory_item import _amount_in_item_units, apply_consumption
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.store_product_alias import StoreProductAlias
from app.schemas.inventory_item import InventoryItemResponse, QuickAddRequest
from app.schemas.stock import (
    ConsumedFromItem,
    RequestedAmount,
    StockAddResponse,
    StockConsumeRequest,
    StockConsumeResponse,
    StockRow,
)
from app.services import idempotency
from app.services.idempotency import IdempotencyClaim
from app.services.product_lookup import product_for_request
from app.services.quick_add import quick_add
from app.services.units import canonical_factor, quantise, to_canonical_decimal

logger = get_logger(__name__)

#: A product whose earliest item expires within this many days (or already has) is expiring.
EXPIRING_WITHIN_DAYS = 3


class InvalidConsume(ValueError):
    """The request cannot be applied to this stock as asked."""


class IncompatibleUnit(InvalidConsume):
    """The unit is a different kind of measure from every item there is (g against pcs)."""


class InsufficientStock(Exception):
    """Less is there than was asked for, and a partial consume was not allowed."""

    def __init__(self, available: Decimal, unit: str) -> None:
        super().__init__(f"Only {available} {unit} available")
        self.available = available
        self.unit = unit


async def _products_matching(db: AsyncSession, q: str) -> set[UUID]:
    """Products whose canonical, learned or printed name contains ``q``, any case."""
    learned = select(ProductName.product_master_id).where(
        ProductName.name.icontains(q, autoescape=True)
    )
    printed = select(StoreProductAlias.product_master_id).where(
        StoreProductAlias.receipt_name.icontains(q, autoescape=True)
    )
    rows = await db.execute(
        select(ProductMaster.id).where(
            or_(
                ProductMaster.canonical_name.icontains(q, autoescape=True),
                ProductMaster.id.in_(learned),
                ProductMaster.id.in_(printed),
            )
        )
    )
    return set(rows.scalars().all())


async def stock_summary(
    db: AsyncSession,
    *,
    q: str | None = None,
    location: str | None = None,
    expiring_days: int | None = None,
    category: str | None = None,
) -> list[StockRow]:
    """One row per product and unit with stock in the kitchen, soonest to expire first.

    ``location`` counts only that location's items; ``expiring_days`` keeps the products
    whose earliest expiry is at most that many days away.
    """
    items: list[Any] = await crud_inventory.get_inventory_items(db, location=location)
    if q is not None and q.strip():
        wanted = await _products_matching(db, q.strip())
        items = [item for item in items if item.product_master_id in wanted]
    if category:
        items = [item for item in items if item.category == category]

    groups: dict[tuple[UUID, str], list[Any]] = defaultdict(list)
    for item in items:
        groups[(item.product_master_id, str(item.unit))].append(item)

    today = date.today()
    rows: list[StockRow] = []
    for (product_id, unit), group in groups.items():
        locations: dict[str, Decimal] = defaultdict(Decimal)
        for item in group:
            locations[str(item.location)] += Decimal(item.current_quantity)
        first = group[0]
        earliest = min(item.expiry_date for item in group)
        rows.append(
            StockRow(
                product_id=product_id,
                product_name=first.product_name,
                category=first.category,
                category_icon=first.category_icon,
                unit=unit,
                total=sum(locations.values(), Decimal(0)),
                item_count=len(group),
                earliest_expiry=earliest,
                locations=dict(sorted(locations.items())),
                expiring=earliest <= today + timedelta(days=EXPIRING_WITHIN_DAYS),
            )
        )

    if expiring_days is not None:
        limit = today + timedelta(days=expiring_days)
        rows = [row for row in rows if row.earliest_expiry <= limit]
    rows.sort(key=lambda r: (r.earliest_expiry, r.product_name.casefold(), r.unit))
    return rows


async def add_stock(
    db: AsyncSession,
    request: QuickAddRequest,
    *,
    claim: IdempotencyClaim | None = None,
) -> StockAddResponse:
    """Quick add, answered with whether the product was new.

    Quick add commits inside, so a remembered response is stored in a second transaction
    straight after it. The caller holds the key across both (``idempotency.held``), so a
    retry racing this request waits and then replays. Only a crash between the two
    commits leaves the item without its key, and a retry after that adds a second one.

    Raises:
        InvalidProductRequest: unknown product, or a new product without a valid category.
    """
    result = await quick_add(db, request)
    response = StockAddResponse(
        item=InventoryItemResponse.model_validate(result.item),
        product_created=result.product_created,
    )
    if claim is not None:
        try:
            await idempotency.remember(db, claim, 201, response.model_dump(mode="json"))
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    return response


async def consume(
    db: AsyncSession,
    request: StockConsumeRequest,
    *,
    claim: IdempotencyClaim | None = None,
) -> StockConsumeResponse:
    """Consume an amount of a product across its items, first to expire first.

    Items measured in another unit than the request's (a count of cheese slices beside a
    block in grams) are passed over; only when none is left is the unit refused. One commit
    for the lot, so any failure writes nothing, and a dry run rolls the same work back.

    Raises:
        ProductNotFound, AmbiguousProduct: The product could not be named exactly.
        InvalidConsume: The amount rounds to nothing, or the unit fits no item.
        InsufficientStock: Short stock without ``allow_partial``.
    """
    try:
        response = await _consume(db, request)
        if request.dry_run:
            await db.rollback()
        else:
            if claim is not None:
                await idempotency.remember(
                    db, claim, 200, response.model_dump(mode="json")
                )
            await db.commit()
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Stock consumed by name",
        extra={
            "product_id": str(response.product_id),
            "items": len(response.consumed),
            "dry_run": response.dry_run,
        },
    )
    return response


async def _consume(
    db: AsyncSession, request: StockConsumeRequest
) -> StockConsumeResponse:
    product: Any = await product_for_request(
        db, name=request.product, product_id=request.product_id
    )
    items: list[Any] = await crud_inventory.lock_active_items_for_product(
        db, product.id, location=request.location
    )
    _, unit = canonical_factor(request.unit)
    wanted = to_canonical_decimal(request.amount, request.unit) or Decimal(0)
    if wanted <= 0:
        raise InvalidConsume(f"{request.amount} {request.unit} rounds to nothing")

    # tsp and tbsp are canonical in their own right and never convert to dl, so an item
    # is usable only in the request's own canonical unit.
    usable = [item for item in items if canonical_factor(str(item.unit))[1] == unit]
    if items and not usable:
        measured = ", ".join(sorted({str(item.unit) for item in items}))
        raise IncompatibleUnit(
            f"Cannot consume {request.unit} of {product.canonical_name}: "
            f"it is measured in {measured}"
        )

    available = quantise(sum((Decimal(i.current_quantity) for i in usable), Decimal(0)))
    if available <= 0 or (wanted > available and not request.allow_partial):
        raise InsufficientStock(available, unit)

    left = min(wanted, available)
    consumed: list[ConsumedFromItem] = []
    for item in usable:
        if left <= 0:
            break
        take = min(Decimal(item.current_quantity), left)
        if take <= 0:
            continue
        amount = _amount_in_item_units(take, unit, str(item.unit))
        apply_consumption(db, item, amount)
        left -= amount
        consumed.append(
            ConsumedFromItem(
                item_id=item.id,
                amount=amount,
                unit=str(item.unit),
                remaining=Decimal(item.current_quantity),
                status=str(item.status),
            )
        )

    return StockConsumeResponse(
        product_id=product.id,
        product_name=str(product.canonical_name),
        requested=RequestedAmount(amount=request.amount, unit=request.unit),
        consumed=consumed,
        remaining_total=quantise(
            sum((Decimal(i.current_quantity) for i in usable), Decimal(0))
        ),
        unit=unit,
        dry_run=request.dry_run,
    )
