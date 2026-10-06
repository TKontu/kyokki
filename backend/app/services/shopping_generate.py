"""A shopping list from what the kitchen is short of (AG6), and the open list as text.

Two sources. ``low_stock``: every product with a ``min_stock_quantity`` whose active
stock is below it needs ``reorder_quantity``, or the shortfall when that is not set.
``runout`` (CL6): every product the run-out forecast (``services.runout``) says runs out
within ``RUNOUT_WITHIN_DAYS``, or that ran out after regular use, needs
``reorder_quantity``, or a week at its daily rate rounded up to whole units. Needs merge into the open list: an open item for the product is raised to the
need rather than joined by a second one. Everything is written in one commit, together
with the remembered ``Idempotency-Key`` response; a dry run writes nothing. A real run
holds a transaction-scoped advisory lock from before it reads the open list until that
commit, so two at once serialise and the second merges into the first's items.

Also the single-item writes (create, purchase) with their ``Idempotency-Key`` response
stored straight after, and the open list as text.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.shopping_list_item import shopping_list_item as crud_shopping
from app.domain.units import canonical_factor, quantise
from app.models.product_master import ProductMaster
from app.models.shopping_list_item import ShoppingListItem
from app.schemas.runout import RunoutProduct
from app.schemas.shopping_list_item import (
    GENERATE_SOURCES,
    ShoppingGenerateLine,
    ShoppingGenerateResponse,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingPriority,
    ShoppingSource,
)
from app.schemas.stock import StockRow
from app.services import idempotency
from app.services.idempotency import IdempotencyClaim
from app.services.stock import stock_summary

logger = get_logger(__name__)

LOW_STOCK = "low_stock"
RUNOUT = "runout"
#: The sources `generate` understands, as the request schema publishes them.
#: ``recipe`` and ``meal_plan`` wait for AG5.
SOURCES = GENERATE_SOURCES

#: ``runout`` picks a product forecast to run out within this many days of today, and
#: buys this many days of it at its daily rate when it has no ``reorder_quantity``.
RUNOUT_WITHIN_DAYS = 7

#: The one advisory lock every real `generate` takes, whatever its sources.
GENERATE_LOCK = "kyokki:shopping-generate"

ExportFormat = Literal["text", "markdown"]
EXPORT_FORMATS: tuple[ExportFormat, ...] = ("text", "markdown")

GenerateResult = ShoppingGenerateResponse


class InvalidGenerate(ValueError):
    """``sources`` is not a non-empty list of known source names."""


class _Incompatible(Exception):
    """Two units measure different things (g against pcs), or one is unknown."""


def _factor(from_unit: str, to_unit: str) -> Decimal:
    """What one ``from_unit`` is in ``to_unit``, when both measure the same thing.

    Raises:
        _Incompatible: Different canonical units, or an unknown unit.
    """
    try:
        from_factor, from_canonical = canonical_factor(from_unit)
        to_factor, to_canonical = canonical_factor(to_unit)
    except ValueError as exc:
        raise _Incompatible(str(exc)) from exc
    if from_canonical != to_canonical:
        raise _Incompatible(f"{from_unit} is not {to_unit}")
    return from_factor / to_factor


def _amount(value: Decimal) -> Decimal:
    """At the precision the columns store, without trailing zeros (``6``, not ``6.00``)."""
    return quantise(value).normalize() + Decimal(0)


def _check_sources(sources: object) -> list[str]:
    """The sources, when ``sources`` is a non-empty list of known source names.

    Takes any JSON value, so a bare string or an object is refused here with the stable
    error rather than by request validation.

    Raises:
        InvalidGenerate: Not a list, an empty one, or one holding anything but known names.
    """
    known = ", ".join(SOURCES)
    if not isinstance(sources, list) or not sources:
        raise InvalidGenerate(f"sources must be a list naming at least one of: {known}")
    if not all(isinstance(source, str) for source in sources):
        raise InvalidGenerate(f"sources must be names; the sources are {known}")
    unknown = sorted({source for source in sources if source not in SOURCES})
    if unknown:
        raise InvalidGenerate(
            f"Unknown source {', '.join(unknown)}; the sources are {known}"
        )
    return list(sources)


async def _restock_products(db: AsyncSession) -> list[Any]:
    # Any: the models declare untyped `Column`s, which mypy reads as Column[...], not values.
    rows = await db.execute(
        select(ProductMaster)
        .where(ProductMaster.min_stock_quantity.is_not(None))
        .order_by(ProductMaster.canonical_name)
    )
    return list(rows.scalars().all())


def _on_hand(product: Any, rows: list[StockRow]) -> Decimal:
    """Active stock in the product's unit.

    Raises:
        _Incompatible: Some of it is in a unit that cannot be counted in the product's.
    """
    unit = str(product.default_unit)
    total = Decimal(0)
    for row in rows:
        try:
            total += Decimal(row.total) * _factor(row.unit, unit)
        except _Incompatible as exc:
            raise _Incompatible(
                f"stock in {row.unit} cannot be counted against min_stock in {unit}"
            ) from exc
    return total


def _open_item_for(items: list[Any], unit: str) -> tuple[Any, Decimal] | None:
    """The first open item whose unit the need can be written in, with that factor."""
    for item in items:
        try:
            return item, _factor(unit, str(item.unit))
        except _Incompatible:
            continue
    return None


async def _low_stock(
    db: AsyncSession, response: ShoppingGenerateResponse, *, dry_run: bool
) -> None:
    by_product: dict[UUID, list[StockRow]] = defaultdict(list)
    for row in await stock_summary(db):
        by_product[row.product_id].append(row)

    for product in await _restock_products(db):
        unit = str(product.default_unit)
        min_stock = Decimal(product.min_stock_quantity)
        line: dict[str, Any] = {
            "product_id": product.id,
            "name": product.canonical_name,
            "unit": unit,
            "min_stock": _amount(min_stock),
        }
        try:
            on_hand = _on_hand(product, by_product.get(product.id, []))
        except _Incompatible as exc:
            response.skipped.append(ShoppingGenerateLine(**line, reason=str(exc)))
            continue
        if on_hand >= min_stock:
            continue

        reorder = product.reorder_quantity
        need = _amount(Decimal(reorder) if reorder is not None else min_stock - on_hand)
        line.update(need=need, on_hand=_amount(on_hand))
        if need <= 0:
            continue
        await _merge(db, response, product, line, need, dry_run=dry_run)


async def _merge(
    db: AsyncSession,
    response: ShoppingGenerateResponse,
    product: Any,
    line: dict[str, Any],
    need: Decimal,
    *,
    dry_run: bool,
) -> None:
    """Merge ``need`` (in the product's unit) into the open list, and file the line.

    An open item of the product is raised to the need (``updated``) or left alone when it
    already holds it (``unchanged``); without one a new item is added. An open item in a
    unit that cannot hold the need is left as it is and the product ``skipped``.
    """
    unit = str(product.default_unit)
    open_items: list[Any] = await crud_shopping.get_by_product(
        db, product_master_id=product.id
    )
    existing = _open_item_for(open_items, unit)
    if existing is None and open_items:
        # This reason replaces a runout line's own: the item is why nothing happened.
        response.skipped.append(
            ShoppingGenerateLine(
                **{
                    **line,
                    "item_id": open_items[0].id,
                    "reason": (
                        f"the open list item is in {open_items[0].unit}, "
                        f"which cannot hold a need in {unit}"
                    ),
                }
            )
        )
        return

    if existing is None:
        item_id = None
        if not dry_run:
            item: Any = await crud_shopping.stage(
                db,
                obj_in=ShoppingListItemCreate(
                    product_master_id=product.id,
                    name=str(product.canonical_name),
                    quantity=need,
                    unit=unit,
                    priority=ShoppingPriority.NORMAL,
                    source=ShoppingSource.AUTO_RESTOCK,
                ),
            )
            item_id = item.id
        response.added.append(ShoppingGenerateLine(**line, item_id=item_id))
        return

    item, factor = existing
    wanted = quantise(need * factor)
    if Decimal(item.quantity) >= wanted:
        response.unchanged.append(ShoppingGenerateLine(**line, item_id=item.id))
        return
    if not dry_run:
        item.quantity = wanted
    response.updated.append(ShoppingGenerateLine(**line, item_id=item.id))


def _week_at(rate: Decimal) -> Decimal:
    """``RUNOUT_WITHIN_DAYS`` of use at ``rate``, rounded up to whole units (whole pieces
    for a count unit), at least one."""
    days = (rate * RUNOUT_WITHIN_DAYS).to_integral_value(rounding=ROUND_CEILING)
    return max(Decimal(1), days)


def _picked(response: ShoppingGenerateResponse) -> set[UUID]:
    lines = response.added + response.updated + response.unchanged + response.skipped
    return {line.product_id for line in lines}


async def _runout(
    db: AsyncSession, response: ShoppingGenerateResponse, *, dry_run: bool
) -> None:
    """Products the forecast says run out within ``RUNOUT_WITHIN_DAYS``, or that ran out
    after regular use (``out`` with a daily rate; ``out`` without one, and
    ``insufficient_history``, are left alone)."""
    # Imported here: services.runout imports this module's unit helpers at its top.
    from app.services import runout

    # Low stock wins: a product it already filed a line for (added, raised, unchanged or
    # skipped) is not looked at again, so one run never gives a product two lines.
    already = _picked(response)
    now = datetime.now(UTC)
    today = now.astimezone(runout.TZ).date()
    forecasts: list[tuple[RunoutProduct, Decimal]] = [
        (f, Decimal(f.daily_rate))
        for f in await runout.forecast(db, now=now, include_out=True)
        if f.product_id not in already
        and f.daily_rate is not None
        and f.daily_rate > 0
        and f.days_left is not None
        and f.days_left <= RUNOUT_WITHIN_DAYS
    ]
    if not forecasts:
        return
    rows = await db.execute(
        select(ProductMaster).where(
            ProductMaster.id.in_([f.product_id for f, _ in forecasts])
        )
    )
    products: dict[UUID, Any] = {}
    found: Any
    for found in rows.scalars().all():
        products[found.id] = found

    for f, rate in forecasts:
        product = products[f.product_id]
        unit = str(product.default_unit)
        out = f.status == "out"
        # Already out: no runs_out_on from the forecast (days_left is 0), so today.
        runs_out_on = f.runs_out_on or today
        min_stock = product.min_stock_quantity
        line: dict[str, Any] = {
            "product_id": product.id,
            "name": product.canonical_name,
            "unit": unit,
            "on_hand": _amount(Decimal(f.active_stock)),
            # 0 for a product with no minimum: the line schema requires one.
            "min_stock": _amount(Decimal(min_stock if min_stock is not None else 0)),
            "runs_out_on": runs_out_on,
        }
        try:
            _factor(unit, unit)
        except _Incompatible:
            response.skipped.append(
                ShoppingGenerateLine(
                    **line, reason=f"{unit} is not a unit a need can be written in"
                )
            )
            continue

        reorder = product.reorder_quantity
        need = _amount(Decimal(reorder) if reorder is not None else _week_at(rate))
        if need <= 0:
            continue
        line["need"] = need
        line["reason"] = (
            f"ran out after using {_amount(rate)} {unit} a day"
            if out
            else (
                f"runs out around {runs_out_on.isoformat()} at "
                f"{_amount(rate)} {unit} a day"
            )
        )
        await _merge(db, response, product, line, need, dry_run=dry_run)


async def generate(
    db: AsyncSession,
    sources: object,
    *,
    dry_run: bool,
    claim: IdempotencyClaim | None = None,
) -> GenerateResult:
    """Work out what the kitchen needs and merge it into the open shopping list.

    One commit for every item added or raised, and for the remembered response when a
    claim is given. A real run takes the generate lock first and holds it to that commit,
    so a second run at the same time waits and then sees these items. A dry run computes
    the same result without the lock and rolls back.

    Raises:
        InvalidGenerate: ``sources`` is not a non-empty list of known source names.
    """
    names = _check_sources(sources)
    response = ShoppingGenerateResponse(dry_run=dry_run)
    try:
        if not dry_run:
            await db.execute(
                select(
                    func.pg_advisory_xact_lock(func.hashtextextended(GENERATE_LOCK, 0))
                )
            )
        if LOW_STOCK in names:
            await _low_stock(db, response, dry_run=dry_run)
        if RUNOUT in names:
            # After low stock, which wins a product both pick (see `_runout`).
            await _runout(db, response, dry_run=dry_run)
        if dry_run:
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
        "Shopping list generated",
        extra={
            "sources": names,
            "dry_run": dry_run,
            "added": len(response.added),
            "updated": len(response.updated),
            "unchanged": len(response.unchanged),
            "skipped": len(response.skipped),
        },
    )
    return response


async def _remember(
    db: AsyncSession, claim: IdempotencyClaim | None, status_code: int, item: Any
) -> None:
    """Store the answer for ``claim`` in a commit of its own; nothing without a claim.

    The item's write has already committed (the CRUD layer commits), so the caller holds
    the key across both with ``idempotency.held``: a racing retry waits, then replays.
    """
    if claim is None:
        return
    body = ShoppingListItemResponse.model_validate(item).model_dump(mode="json")
    try:
        await idempotency.remember(db, claim, status_code, body)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def create_item(
    db: AsyncSession,
    item_in: ShoppingListItemCreate,
    *,
    claim: IdempotencyClaim | None = None,
) -> ShoppingListItem:
    """Add one item to the list, and remember the 201 answer when a claim is given.

    A refused write (an unknown product) rolls back and is not remembered.
    """
    try:
        item = await crud_shopping.create(db, obj_in=item_in)
    except BaseException:
        await db.rollback()
        raise
    await _remember(db, claim, 201, item)
    return item


async def mark_purchased(
    db: AsyncSession,
    item_id: UUID,
    *,
    purchased: bool,
    claim: IdempotencyClaim | None = None,
) -> ShoppingListItem | None:
    """Mark one item bought (or not), and remember the answer when a claim is given.

    None when there is no such item; that is not remembered.
    """
    item = await crud_shopping.mark_purchased(db, item_id=item_id, purchased=purchased)
    if item is not None:
        await _remember(db, claim, 200, item)
    return item


def _quantity(value: Any) -> str:
    return format(_amount(Decimal(value)), "f")


def render_export(items: Sequence[ShoppingListItem], fmt: str) -> str:
    """The open list as plain text (``- name quantity unit``) or a Markdown checklist
    (``- [ ] name (quantity unit)``), one line per item, in the order given.

    Raises:
        ValueError: An unknown format.
    """
    _check_format(fmt)
    if fmt == "text":
        lines = [f"- {i.name} {_quantity(i.quantity)} {i.unit}" for i in items]
    else:
        lines = [f"- [ ] {i.name} ({_quantity(i.quantity)} {i.unit})" for i in items]
    return "".join(f"{line}\n" for line in lines)


def _check_format(fmt: str) -> None:
    if fmt not in EXPORT_FORMATS:
        raise ValueError(
            f"Unknown format {fmt!r}; the formats are {', '.join(EXPORT_FORMATS)}"
        )


async def export(db: AsyncSession, fmt: str) -> str:
    """The open list, urgent first and then by name, rendered in ``fmt``.

    Raises:
        ValueError: An unknown format.
    """
    _check_format(fmt)
    return render_export(await crud_shopping.get_open(db), fmt)
