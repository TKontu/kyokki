"""When each product will run out, from its own recent history (Phase 3 "Consumption
Learning", frontier item 8, `docs/TODO.md`).

Deliberately simple - no seasonality, no model fit, just a straight-line average::

    daily_rate = (quantity consumed in a lookback window) / (days spanned by it)
    runs_out_on = today + active_stock / daily_rate

"Consumed" is ``use_partial`` and ``use_full`` only
(``schemas.consumption_log.ConsumptionAction``): a discard is waste, not use, and never
feeds the rate; ``restore`` and ``correct`` are neither and are ignored too. An undone
row never reaches this at all - the general undo (``services.undo``) deletes it outright
on reversal, so a plain read of ``consumption_log`` already excludes it (H46); there is
nothing here to filter.

The lookback window is ``DEFAULT_WINDOW_DAYS`` (60 days, up to now), but it does not
start 60 empty days before a product's first-ever purchase: it starts at the first
consume event *within* that window, so a product bought last week is judged on a week,
not diluted across two months of nothing before it existed. That span is floored at
``MIN_WINDOW_DAYS`` (7), so one or two events in the last day or two cannot imply an
absurd daily rate.

"Enough history" to trust a rate at all is ``MIN_EVENTS`` (3) consume events on at least
``MIN_DISTINCT_DAYS`` (2) distinct calendar days, binned in ``TZ`` (Europe/Helsinki, the
app's timezone - the same one ``services.waste_stats`` bins its weeks in). Short of that,
the product reports ``insufficient_history`` rather than a rate guessed from one or two
points.

Quantities are converted into the product's own unit (``ProductMaster.default_unit``),
reusing ``services.shopping_generate``'s own ``_factor``/``_Incompatible`` - the same
pair ``services.min_stock`` already imports across module boundaries for the same reason
(do not restate a unit-compatibility check that already exists). A logged row in a unit
that cannot convert to the product's is skipped from both the sum and the event count -
it cannot be counted toward "how much" and "how often" at the same time, so it would
otherwise inflate one without the other - and the number skipped is logged, not
returned: the API shape has no room for it, and it is deliberately an edge case rather
than a tracked metric.

Active stock is ``services.shopping_generate``'s own ``_on_hand`` (do not restate it
either): the same per-product total, in the product's unit, that auto-restock and
shopping-generate already use. A product whose stock is partly in a unit that cannot
convert to its own is left out of the result entirely, exactly as ``shopping_generate``
skips it rather than guess.

``runs_out_on`` is null exactly when there is no stock left (``status`` is then ``out``)
or the rate is 0 (the product is still ``forecast``, just with no end in sight at the
current pace). ``expires_first`` compares ``runs_out_on`` against the earliest expiry
date among the product's active items (``services.stock.stock_summary``'s own field per
product/unit group, the smallest taken across a product's groups) - set only when both
a run-out date and an expiry exist and the expiry comes first, so "you will not finish it
in time" is never guessed from one date alone.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.consumption_log import ConsumptionLog
from app.models.product_master import ProductMaster
from app.schemas.consumption_log import ConsumptionAction
from app.schemas.runout import RunoutProduct, RunoutStatus
from app.schemas.stock import StockRow
from app.services.shopping_generate import _factor as _conversion_factor
from app.services.shopping_generate import _Incompatible as Incompatible
from app.services.shopping_generate import _on_hand as _active_stock
from app.services.stock import stock_summary
from app.services.units import quantise

logger = get_logger(__name__)

#: The app's timezone (docker-compose.yml ``TZ``), as ``services.waste_stats`` uses it -
#: not read from settings, which has no such setting to extend.
TZ = ZoneInfo("Europe/Helsinki")

DEFAULT_WINDOW_DAYS = 60
MIN_WINDOW_DAYS = 7
MIN_EVENTS = 3
MIN_DISTINCT_DAYS = 2

_CONSUME_ACTIONS = (
    ConsumptionAction.USE_PARTIAL.value,
    ConsumptionAction.USE_FULL.value,
)


def _today(now: datetime) -> date:
    return now.astimezone(TZ).date()


async def _consume_rows(
    db: AsyncSession, product_id: UUID, floor: datetime
) -> list[Any]:
    """Every consume event for ``product_id`` at or after ``floor``, oldest first."""
    rows = await db.execute(
        select(
            ConsumptionLog.quantity_consumed,
            ConsumptionLog.unit,
            ConsumptionLog.logged_at,
        )
        .where(
            ConsumptionLog.product_master_id == product_id,
            ConsumptionLog.action.in_(_CONSUME_ACTIONS),
            ConsumptionLog.logged_at >= floor,
        )
        .order_by(ConsumptionLog.logged_at)
    )
    return list(rows.all())


def _summarize(rows: list[Any], unit: str) -> tuple[Decimal, datetime | None, int, int]:
    """``(total consumed in unit, first event, event count, distinct days)`` over rows
    that convert into ``unit``; one that cannot is skipped from every figure."""
    total = Decimal(0)
    seen_days: set[date] = set()
    first_at: datetime | None = None
    events = 0
    skipped = 0
    for quantity, row_unit, logged_at in rows:
        try:
            factor = _conversion_factor(str(row_unit), unit)
        except Incompatible:
            skipped += 1
            continue
        total += Decimal(str(quantity)) * factor
        events += 1
        seen_days.add(logged_at.astimezone(TZ).date())
        if first_at is None:
            first_at = logged_at
    if skipped:
        logger.debug(
            "runout: skipped consumption rows in an inconvertible unit",
            extra={"unit": unit, "skipped": skipped},
        )
    return total, first_at, events, len(seen_days)


async def _candidate_product_ids(db: AsyncSession, floor: datetime) -> set[UUID]:
    """Products consumed from at all within the lookback window - a candidate even
    without enough history yet, so it can still report ``insufficient_history``."""
    rows = await db.execute(
        select(ConsumptionLog.product_master_id)
        .where(
            ConsumptionLog.action.in_(_CONSUME_ACTIONS),
            ConsumptionLog.logged_at >= floor,
        )
        .distinct()
    )
    return set(rows.scalars().all())


async def _load_products(db: AsyncSession, ids: set[UUID]) -> list[Any]:
    if not ids:
        return []
    rows = await db.execute(select(ProductMaster).where(ProductMaster.id.in_(ids)))
    return list(rows.scalars().all())


async def _one(
    db: AsyncSession,
    product: Any,
    active_stock: Decimal,
    earliest_expiry: date | None,
    *,
    floor: datetime,
    today: date,
) -> RunoutProduct:
    unit = str(product.default_unit)
    name = str(product.canonical_name)
    active_stock = quantise(active_stock)

    rows = await _consume_rows(db, product.id, floor)
    total, first_at, events, distinct_days = _summarize(rows, unit)
    enough = events >= MIN_EVENTS and distinct_days >= MIN_DISTINCT_DAYS

    status: RunoutStatus
    if active_stock <= 0:
        status = "out"
    elif not enough:
        status = "insufficient_history"
    else:
        status = "forecast"

    rate: Decimal | None = None
    if enough and first_at is not None:
        span_days = max(MIN_WINDOW_DAYS, (today - first_at.astimezone(TZ).date()).days)
        rate = quantise(total / span_days)

    runs_out_on: date | None = None
    days_left: int | None = None
    if status == "out":
        days_left = 0
    elif rate is not None and rate > 0:
        days_left = int((active_stock / rate).to_integral_value(rounding=ROUND_HALF_UP))
        runs_out_on = today + timedelta(days=days_left)

    expires_first = (
        runs_out_on is not None
        and earliest_expiry is not None
        and earliest_expiry < runs_out_on
    )

    return RunoutProduct(
        product_id=product.id,
        name=name,
        unit=unit,
        active_stock=active_stock,
        daily_rate=rate,
        runs_out_on=runs_out_on,
        days_left=days_left,
        expires_first=expires_first,
        status=status,
    )


def _sort_key(item: RunoutProduct) -> tuple[bool, int, str]:
    # Soonest first; a product with no days_left to compare (insufficient_history)
    # sorts after every one that has.
    return (
        item.days_left is None,
        item.days_left if item.days_left is not None else 0,
        item.name.casefold(),
    )


async def forecast(
    db: AsyncSession,
    *,
    within_days: int | None = None,
    now: datetime | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> list[RunoutProduct]:
    """Every product with a forecast to report, soonest to run out first.

    ``within_days`` filters to products whose ``days_left`` is at most that many days -
    which excludes ``insufficient_history`` (no ``days_left`` to compare) by the same
    read, not a second special case. ``now`` is for tests; the endpoints leave it at the
    real clock.
    """
    anchor = now or datetime.now(UTC)
    today = _today(anchor)
    floor = anchor - timedelta(days=window_days)

    stock_rows = await stock_summary(db)
    by_product: dict[UUID, list[StockRow]] = defaultdict(list)
    for row in stock_rows:
        by_product[row.product_id].append(row)

    candidate_ids = set(by_product) | await _candidate_product_ids(db, floor)
    if not candidate_ids:
        return []

    results: list[RunoutProduct] = []
    for product in await _load_products(db, candidate_ids):
        rows = by_product.get(product.id, [])
        try:
            active_stock = _active_stock(product, rows)
        except Incompatible:
            logger.debug(
                "runout: skipped a product whose stock is partly in an "
                "inconvertible unit",
                extra={"product_id": str(product.id)},
            )
            continue
        earliest_expiry = min((row.earliest_expiry for row in rows), default=None)
        results.append(
            await _one(
                db, product, active_stock, earliest_expiry, floor=floor, today=today
            )
        )

    if within_days is not None:
        results = [
            r for r in results if r.days_left is not None and r.days_left <= within_days
        ]

    results.sort(key=_sort_key)
    return results
