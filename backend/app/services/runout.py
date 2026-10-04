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

Only days on which the product had stock count toward that span. A day with nothing in
the kitchen cannot be a consumption day, so milk used daily for ten days, then out of
stock for a month, then restocked two days ago is judged on its thirteen in-stock days,
not on the six weeks the calendar spans. A day on which it *was* in stock but went unused
is real low use and still counts - which is why the rule reads stock history, not the
gaps between consume events (those cannot tell the two apart). Precisely::

    span = max(MIN_WINDOW_DAYS,
               the calendar days d (in TZ), first consume day <= d < today,
               on which at least one of the product's items was in active stock)

so a product in stock the whole time gets exactly the calendar span
``today - first consume day``. An item's time in stock is rebuilt from its own columns
and its log rows, in time order: it enters at ``created_at``; it leaves at a ``discard``
row's ``logged_at`` and re-enters at a ``restore`` row's; one now ``empty`` or
``discarded`` left for the last time at ``consumed_at``; one still active is in stock up
to now. A day counts if any part of it lies inside one of those intervals. An exit the
history does not record (``consumed_at`` keeps only the latest one, and an item that went
empty and was then corrected back up has no row for the first) leaves the item counted as
in stock, which can only lengthen the span. An undo needs no handling here: it deletes
the rows it reverses and puts the item's columns back (``services.undo``), so what is
left reads as if the reversed event never happened.

**Fallback.** Where the history cannot account for the use - any counted consume event
falls on a day on which no item of the product was in stock, as with data logged before
these columns were kept, or by an item since deleted - the product falls back to the plain
calendar span ``today - first consume day``, floored as above. A span is never shortened
from guesswork.

``forecast`` runs a fixed number of statements however many products it reports: the
stock summary, the consume rows of every product at once (which also name the
candidates), the products, and two for the stock history (the items, then their
``discard``/``restore`` rows). Everything else is grouped in Python.

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

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.consumption_log import ConsumptionAction
from app.schemas.inventory_item import InventoryStatus
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
#: The log rows that take an item out of stock and put it back.
_STOCK_MOVE_ACTIONS = (
    ConsumptionAction.DISCARD.value,
    ConsumptionAction.RESTORE.value,
)
#: Not active stock: the same pair as ``crud.inventory_item.INACTIVE_STATUSES``, named
#: from the status vocabulary (``schemas.inventory_item.InventoryStatus``).
_INACTIVE_STATUSES = (
    InventoryStatus.EMPTY.value,
    InventoryStatus.DISCARDED.value,
)


def _today(now: datetime) -> date:
    return now.astimezone(TZ).date()


async def _consume_rows(db: AsyncSession, floor: datetime) -> dict[UUID, list[Any]]:
    """Every consume event at or after ``floor``, oldest first, grouped by product.

    A product with any is a candidate even without enough history yet, so it can still
    report ``insufficient_history``.
    """
    rows = await db.execute(
        select(
            ConsumptionLog.product_master_id,
            ConsumptionLog.quantity_consumed,
            ConsumptionLog.unit,
            ConsumptionLog.logged_at,
        )
        .where(
            ConsumptionLog.action.in_(_CONSUME_ACTIONS),
            ConsumptionLog.logged_at >= floor,
        )
        .order_by(ConsumptionLog.logged_at)
    )
    grouped: dict[UUID, list[Any]] = defaultdict(list)
    for product_id, quantity, unit, logged_at in rows.all():
        grouped[product_id].append((quantity, unit, logged_at))
    return grouped


async def _in_stock_days(
    db: AsyncSession, product_ids: set[UUID], *, floor: datetime, anchor: datetime
) -> dict[UUID, set[date]]:
    """Per product, the calendar days (in ``TZ``) from ``floor`` to ``anchor`` on which
    at least one of its items was in active stock - the module docstring's rule.

    Two statements: the items that could have been in stock inside the window, then
    their ``discard``/``restore`` rows.
    """
    if not product_ids:
        return {}
    items = (
        await db.execute(
            select(
                InventoryItem.id,
                InventoryItem.product_master_id,
                InventoryItem.status,
                InventoryItem.created_at,
                InventoryItem.consumed_at,
            ).where(
                InventoryItem.product_master_id.in_(product_ids),
                InventoryItem.created_at <= anchor,
                or_(
                    InventoryItem.consumed_at.is_(None),
                    InventoryItem.consumed_at >= floor,
                ),
            )
        )
    ).all()
    if not items:
        return {}

    moves: dict[UUID, list[tuple[datetime, bool]]] = defaultdict(list)
    log_rows = await db.execute(
        select(
            ConsumptionLog.inventory_item_id,
            ConsumptionLog.action,
            ConsumptionLog.logged_at,
        ).where(
            ConsumptionLog.inventory_item_id.in_([item.id for item in items]),
            ConsumptionLog.action.in_(_STOCK_MOVE_ACTIONS),
            ConsumptionLog.logged_at <= anchor,
        )
    )
    for item_id, action, logged_at in log_rows.all():
        moves[item_id].append((logged_at, action == ConsumptionAction.RESTORE.value))

    floor_day = _today(floor)
    days: dict[UUID, set[date]] = defaultdict(set)
    for item_id, product_id, status, created_at, consumed_at in items:
        for start, end in _intervals(
            created_at,
            moves.get(item_id, []),
            active=str(status) not in _INACTIVE_STATUSES,
            consumed_at=consumed_at,
            anchor=anchor,
        ):
            day = max(_today(start), floor_day)
            last = _today(end)
            while day <= last:
                days[product_id].add(day)
                day += timedelta(days=1)
    return days


def _intervals(
    created_at: datetime,
    moves: list[tuple[datetime, bool]],
    *,
    active: bool,
    consumed_at: datetime | None,
    anchor: datetime,
) -> list[tuple[datetime, datetime]]:
    """One item's time in stock. ``moves`` are ``(when, entered)``: a restore enters, a
    discard leaves. An exit with no record leaves the item in stock up to ``anchor``."""
    events = [(created_at, True), *moves]
    if not active and consumed_at is not None:
        events.append((consumed_at, False))
    # At the same instant an entry goes first, so that day still counts.
    events.sort(key=lambda event: (event[0], not event[1]))

    intervals: list[tuple[datetime, datetime]] = []
    started: datetime | None = None
    last_at = created_at
    for at, entered in events:
        last_at = at
        if entered and started is None:
            started = at
        elif not entered and started is not None:
            intervals.append((started, at))
            started = None
    if started is None and active:
        # Active now although the rows end on an exit: the status wins over the rows.
        started = last_at
    if started is not None:
        intervals.append((started, anchor))
    return intervals


def _span_days(
    first_at: datetime, event_days: set[date], in_stock: set[date] | None, today: date
) -> int:
    """The module docstring's span: in-stock days from the first consume day up to
    today, or the calendar span when the history cannot account for every event."""
    first_day = first_at.astimezone(TZ).date()
    if in_stock and event_days <= in_stock:
        span = sum(1 for day in in_stock if first_day <= day < today)
    else:
        span = (today - first_day).days
    return max(MIN_WINDOW_DAYS, span)


def _summarize(
    rows: list[Any], unit: str
) -> tuple[Decimal, datetime | None, int, set[date]]:
    """``(total consumed in unit, first event, event count, the days with an event)``
    over rows that convert into ``unit``; one that cannot is skipped from every figure."""
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
    return total, first_at, events, seen_days


async def _load_products(db: AsyncSession, ids: set[UUID]) -> list[Any]:
    if not ids:
        return []
    rows = await db.execute(select(ProductMaster).where(ProductMaster.id.in_(ids)))
    return list(rows.scalars().all())


def _one(
    product: Any,
    active_stock: Decimal,
    earliest_expiry: date | None,
    rows: list[Any],
    in_stock: set[date] | None,
    *,
    today: date,
) -> RunoutProduct:
    unit = str(product.default_unit)
    name = str(product.canonical_name)
    active_stock = quantise(active_stock)

    total, first_at, events, event_days = _summarize(rows, unit)
    enough = events >= MIN_EVENTS and len(event_days) >= MIN_DISTINCT_DAYS

    status: RunoutStatus
    if active_stock <= 0:
        status = "out"
    elif not enough:
        status = "insufficient_history"
    else:
        status = "forecast"

    rate: Decimal | None = None
    if enough and first_at is not None:
        span_days = _span_days(first_at, event_days, in_stock, today)
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
    include_out: bool = False,
) -> list[RunoutProduct]:
    """Every product with a forecast to report, soonest to run out first.

    A run-out list answers "what will run out soon", not "what is gone": a product
    already at zero stock (``status`` ``out``) is dropped unless ``include_out`` is
    set, with or without ``within_days`` - an ``out`` item has ``days_left`` 0, which
    would otherwise pass any non-negative ``within_days`` and drown out real forecasts
    (the production shape this guards: 28 ``out`` items and one real forecast).

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

    consumed = await _consume_rows(db, floor)
    candidate_ids = set(by_product) | set(consumed)
    if not candidate_ids:
        return []
    in_stock = await _in_stock_days(db, set(consumed), floor=floor, anchor=anchor)

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
            _one(
                product,
                active_stock,
                earliest_expiry,
                consumed.get(product.id, []),
                in_stock.get(product.id),
                today=today,
            )
        )

    if not include_out:
        results = [r for r in results if r.status != "out"]

    if within_days is not None:
        results = [
            r for r in results if r.days_left is not None and r.days_left <= within_days
        ]

    results.sort(key=_sort_key)
    return results
