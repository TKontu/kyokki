"""Stock as an agent sees it: per product, added by name, consumed by name (AG2).

Thin on purpose. Consuming applies the single-item consume's rules
(`crud.inventory_item.apply_consumption`) to each item in turn, first to expire first, in
one transaction. The iPad's item-by-item routes are untouched.

Adding and discarding-expired both store their Idempotency-Key answer in the same
transaction as the write they answer for, before the commit the caller broadcasts after
(Q24): a crash during that broadcast, even a Redis hang, leaves nothing uncommitted for a
retry to duplicate. Adding cannot reuse `services.quick_add.quick_add` for this - it commits
(and, when a typed date re-dates a sibling, broadcasts) on its own - so it calls the same
primitives quick add is built from instead, one transaction later.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.crud.consumption_log import ConsumptionAction, add_consumption_log
from app.crud.inventory_item import _amount_in_item_units, apply_consumption
from app.crud.product_master import MovedInventoryItem
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.store_product_alias import StoreProductAlias
from app.schemas.inventory_item import InventoryItemResponse, QuickAddRequest
from app.schemas.stock import (
    ConsumedFromItem,
    DiscardedStockItem,
    DiscardExpiredResponse,
    RequestedAmount,
    StockAddResponse,
    StockConsumeRequest,
    StockConsumeResponse,
    StockRow,
)
from app.services import idempotency
from app.services.generic_products import (
    ProductResolver,
    build_inventory_item,
)
from app.services.idempotency import IdempotencyClaim
from app.services.item_status import ItemEvent, ItemFrozen, next_status
from app.services.product_lookup import product_for_request
from app.services.shelf_life_learning import learn_from_item, lock_product
from app.services.units import canonical_factor, quantise, to_canonical_decimal

logger = get_logger(__name__)

#: A product whose earliest item expires within this many days (or already has) is expiring.
EXPIRING_WITHIN_DAYS = 3

#: The same "past its date" rule as the iPad's expired shelf (`frontend/lib/fridge.ts`,
#: `calculateDaysUntilExpiry(...) < 0`): an active item whose expiry is strictly before
#: today, i.e. at or before yesterday.
EXPIRED_WITHIN_DAYS = -1


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


@dataclass
class AddStockResult:
    """`add_stock`'s answer, plus what a re-dated sibling needs for its own broadcast."""

    response: StockAddResponse
    moved: list[MovedInventoryItem] = field(default_factory=list)
    product_created: bool = False


@dataclass
class DiscardExpiredResult:
    """`discard_expired`'s answer, plus what changed for the caller's broadcast."""

    response: DiscardExpiredResponse
    changed: list[MovedInventoryItem] = field(default_factory=list)


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
) -> AddStockResult:
    """Quick add, answered with whether the product was new.

    Built from the same primitives as `services.quick_add.quick_add` - find or create the
    product, build a sealed item, learn from a typed date if one was given - but committed
    once, together with the Idempotency-Key's stored answer (Q24). Quick add itself cannot
    be reused here: it commits on its own, and - when a typed date re-dates a sibling -
    broadcasts that before it can return, which would leave the item committed with no key
    for a retry to find if the broadcast then failed (a Redis hang is enough; it need not
    raise). Here nothing is broadcast until the caller holds this answer and the
    transaction storing it has committed.

    Raises:
        InvalidProductRequest: unknown product, or a new product without a valid category.
    """
    try:
        product, created = await ProductResolver(db).resolve(
            product_id=request.product_id,
            name=request.name,
            category=request.category,
            unit=request.unit,
            quantity=request.quantity,
        )
        if request.expiry_date is not None:
            # The product before the item: the insert takes a key-share lock on it, and
            # learning then needs it for update (see `lock_product`).
            await lock_product(db, cast(UUID, product.id))
        item = build_inventory_item(
            product,
            quantity=request.quantity,
            unit=request.unit,
            purchase_date=request.purchase_date or date.today(),
            expiry_date=request.expiry_date,
            location=request.location,
        )
        db.add(item)
        await db.flush()
        moved: list[MovedInventoryItem] = []
        if request.expiry_date is not None:
            moved = await learn_from_item(db, item)
        # Reload with the product so the response has product and category names, as
        # quick add's own post-commit reload does.
        loaded = await crud_inventory.get_inventory_item(db, cast(UUID, item.id))
        response = StockAddResponse(
            item=InventoryItemResponse.model_validate(loaded), product_created=created
        )
        if claim is not None:
            await idempotency.remember(db, claim, 201, response.model_dump(mode="json"))
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Stock added",
        extra={
            "inventory_item_id": str(item.id),
            "product_id": str(product.id),
            "product_created": created,
            "moved": len(moved),
        },
    )
    return AddStockResult(response=response, moved=moved, product_created=created)


def _discarded_row(item: Any) -> DiscardedStockItem:
    return DiscardedStockItem(
        item_id=item.id,
        product_name=item.product_name,
        amount=Decimal(item.current_quantity),
        unit=str(item.unit),
        expiry_date=item.expiry_date,
        location=item.location,
    )


async def discard_expired(
    db: AsyncSession,
    *,
    location: str | None = None,
    dry_run: bool = False,
    claim: IdempotencyClaim | None = None,
) -> DiscardExpiredResult:
    """Throw away every active item past its expiry date (AG7 task 6, "throw away
    everything expired").

    "Expired" is not restated here: it is the same rule the iPad's expired shelf uses - an
    active item whose expiry is before today - as the `expiring_days=-1` filter already
    shared by `stock_summary`'s own query answers (`crud.get_inventory_items`). A dry run
    only lists what that query finds; a real run moves each item through H23's `discard`
    transition, the one `/inventory/discard` applies, and stores its Idempotency-Key answer
    in the same transaction as those moves, before the commit the caller broadcasts after
    (Q24).
    """
    expired = await crud_inventory.get_inventory_items(
        db, location=location, expiring_days=EXPIRED_WITHIN_DAYS
    )
    response = DiscardExpiredResponse(
        items=[_discarded_row(item) for item in expired],
        count=len(expired),
        dry_run=dry_run,
    )
    if dry_run:
        return DiscardExpiredResult(response=response)

    try:
        changed = await _discard_by_id(db, [cast(UUID, item.id) for item in expired])
        if claim is not None:
            await idempotency.remember(db, claim, 200, response.model_dump(mode="json"))
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Expired stock discarded",
        extra={"count": len(changed), "location": location},
    )
    return DiscardExpiredResult(response=response, changed=changed)


async def _discard_by_id(
    db: AsyncSession, item_ids: list[UUID]
) -> list[MovedInventoryItem]:
    """Discard these items through H23's transition, as `crud.inventory_item.move_many`
    does - but without its own commit, so the caller can store its idempotency answer
    alongside the moves rather than in a transaction after them (Q24).
    """
    if not item_ids:
        return []

    query = (
        select(InventoryItem)
        .where(InventoryItem.id.in_(item_ids))
        .with_for_update(of=InventoryItem)
    )
    found = list((await db.execute(query)).scalars().all())

    batch_id = uuid4()
    changed: list[MovedInventoryItem] = []
    for item in found:
        row: Any = item
        was = str(row.status)
        try:
            new_status = next_status(
                current=was,
                event=ItemEvent.DISCARD,
                initial=Decimal(str(row.initial_quantity)),
                remaining=Decimal(str(row.current_quantity)),
                opened=row.opened_date is not None,
            )
        except ItemFrozen:
            # Already thrown away since the list was built: nothing to do.
            continue
        if new_status == was:
            continue

        remaining = Decimal(str(row.current_quantity))
        add_consumption_log(
            db,
            item=item,
            previous=crud_inventory.snapshot(item),
            batch_id=batch_id,
            action=ConsumptionAction.DISCARD,
            quantity=remaining,
            quantity_after=Decimal(0),
        )
        row.status = new_status
        changed.append(
            MovedInventoryItem(
                id=row.id, current_quantity=row.current_quantity, status=new_status
            )
        )
    return changed


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
