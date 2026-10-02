"""Waste rate and trend (planner ruling, 2026-10-02): "You threw away X of Y things (Z %)."

Counted by events, not amounts - grams and pieces do not add up (`ActionSummary`). A discarded
item that was later restored is not waste: `item_status.is_frozen` freezes an item the moment
it is discarded, and the only way out is an explicit restore (`crud.inventory_item._event_for`,
`services.item_status.next_status`), so an item can never be discarded twice running without a
restore in between. That means "a restore for the same item logged after this discard" can only
be the restore undoing it - no batch bookkeeping is needed to pair them up.

Weeks are ISO weeks (Monday start), binned in Postgres with ``AT TIME ZONE 'Europe/Helsinki'``
(the app's timezone, ``TZ`` in docker-compose.yml) so a Sunday-night event lands in the week it
felt like locally, not the UTC calendar day it happened to be stored under.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import (
    ColumnElement,
    DateTime,
    Integer,
    String,
    and_,
    bindparam,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.category import Category
from app.models.consumption_log import ConsumptionLog
from app.models.product_master import ProductMaster
from app.schemas.consumption_log import ConsumptionAction

#: The app's timezone (docker-compose.yml ``TZ``). Not read from settings: nothing else in the
#: backend needs a timezone, and ``app/core/config.py`` has no such setting to extend.
TZ = "Europe/Helsinki"

TREND_WEEKS = 8
MIN_CATEGORY_EVENTS = 3

_DISCARD = ConsumptionAction.DISCARD.value
_USE_FULL = ConsumptionAction.USE_FULL.value
_RESTORE = ConsumptionAction.RESTORE.value

_Restore = aliased(ConsumptionLog)


def _not_reversed_by_a_restore() -> ColumnElement[bool]:
    """True unless this is a discard that a later restore on the same item undid.

    A discarded item is frozen until an explicit restore (``is_frozen`` in
    ``app/services/item_status.py``), so it cannot be discarded a second time before being
    restored. A restore logged after a discard on the same item can therefore only be the one
    undoing that discard - while the item still exists, matching on ``inventory_item_id``
    is exact.

    ``inventory_item_id`` is ``ON DELETE SET NULL`` (H46): once the item is hard-deleted,
    *every* row that named it - the discard and the restore both - goes to NULL, and they can
    no longer be matched by id. Matching ``NULL = NULL`` would be worse than not matching at
    all: it would pair one deleted item's discard with a different deleted item's restore
    (`consumption_log.previous` holds the item's quantity/status fields, not its id - nothing
    stored survives the delete to tell two deleted items apart, and adding a column is a
    migration, out of scope here). So once both sides are NULL, this falls back to same
    product, same unit, same amount: what "Put it back" on *that* discard would have written -
    the restore returns exactly what was taken away, and nothing can change the amount while
    the item is frozen. This is a best-effort rule, not a guarantee: two different deleted
    items of the same product, same unit, discarded for the same amount, one restored and one
    not, are indistinguishable by it.
    """
    same_item = _Restore.inventory_item_id == ConsumptionLog.inventory_item_id
    same_item_once_deleted = and_(
        _Restore.inventory_item_id.is_(None),
        ConsumptionLog.inventory_item_id.is_(None),
        _Restore.product_master_id == ConsumptionLog.product_master_id,
        _Restore.unit == ConsumptionLog.unit,
        _Restore.quantity_consumed == ConsumptionLog.quantity_consumed,
    )
    reversed_by = (
        select(_Restore.id)
        .where(
            _Restore.action == _RESTORE,
            or_(same_item, same_item_once_deleted),
            _Restore.logged_at > ConsumptionLog.logged_at,
        )
        .exists()
    )
    return (ConsumptionLog.action != _DISCARD) | ~reversed_by


def _countable(since: datetime | None) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = [
        ConsumptionLog.action.in_([_DISCARD, _USE_FULL]),
        _not_reversed_by_a_restore(),
    ]
    if since is not None:
        where.append(ConsumptionLog.logged_at >= since)
    return where


def _rate(discarded: int, total: int) -> float | None:
    return (discarded / total) if total else None


@dataclass(frozen=True)
class CategoryFigures:
    """One category's split, already past the event-count threshold."""

    category: str
    display_name: str
    discarded: int
    finished: int

    @property
    def total(self) -> int:
        return self.discarded + self.finished

    @property
    def rate(self) -> float:
        # total is never 0 here: the query only returns categories past MIN_CATEGORY_EVENTS.
        return self.discarded / self.total


@dataclass(frozen=True)
class WasteFigures:
    """The headline rate for a window, plus every category with enough events to mean something."""

    discarded: int
    finished: int
    categories: list[CategoryFigures]

    @property
    def total(self) -> int:
        return self.discarded + self.finished

    @property
    def rate(self) -> float | None:
        return _rate(self.discarded, self.total)


@dataclass(frozen=True)
class WeekFigures:
    """One ISO week of the trend."""

    week_start: date
    discarded: int
    finished: int

    @property
    def total(self) -> int:
        return self.discarded + self.finished

    @property
    def rate(self) -> float | None:
        return _rate(self.discarded, self.total)


async def waste_figures(
    db: AsyncSession, *, since: datetime | None = None
) -> WasteFigures:
    """The headline rate for a window, plus every category with enough events to mean something.

    One query for the overall counts, one for the per-category breakdown (GROUP BY, no N+1).
    """
    where = _countable(since)

    overall = select(
        func.count().filter(ConsumptionLog.action == _DISCARD).label("discarded"),
        func.count().filter(ConsumptionLog.action == _USE_FULL).label("finished"),
    ).where(*where)
    discarded, finished = (await db.execute(overall)).one()

    by_category = (
        select(
            ProductMaster.category.label("category"),
            func.coalesce(Category.display_name, ProductMaster.category).label(
                "display_name"
            ),
            func.count().filter(ConsumptionLog.action == _DISCARD).label("discarded"),
            func.count().filter(ConsumptionLog.action == _USE_FULL).label("finished"),
        )
        .join(ProductMaster, ProductMaster.id == ConsumptionLog.product_master_id)
        .outerjoin(Category, Category.id == ProductMaster.category)
        .where(*where)
        .group_by(ProductMaster.category, Category.display_name)
        .having(func.count() >= MIN_CATEGORY_EVENTS)
    )
    categories = [
        CategoryFigures(
            category=row.category,
            display_name=row.display_name,
            discarded=row.discarded,
            finished=row.finished,
        )
        for row in (await db.execute(by_category)).all()
    ]
    # Worst waste rate first - the Gone screen's "categories that waste the most".
    categories.sort(key=lambda c: (-c.rate, -c.total, c.display_name))

    return WasteFigures(
        discarded=discarded or 0, finished=finished or 0, categories=categories
    )


# generate_series runs the last `weeks` ISO weeks server-side, each left-joined to its
# discard/use_full counts (restores already excluded by the NOT EXISTS) - one query, no
# per-week round trip.
_TREND_SQL = text(
    """
    WITH bounds AS (
        SELECT date_trunc('week', (:now)::timestamptz AT TIME ZONE :tz) AS current_week
    ),
    weeks AS (
        SELECT generate_series(
            (SELECT current_week FROM bounds) - make_interval(weeks => :back),
            (SELECT current_week FROM bounds),
            interval '1 week'
        )::date AS week_start
    ),
    countable AS (
        -- Restore pairing: see _not_reversed_by_a_restore()'s docstring for why, once a
        -- deleted item nulls both rows' inventory_item_id, this falls back to same
        -- product/unit/amount rather than matching NULL = NULL across unrelated items.
        SELECT
            cl.action,
            (date_trunc('week', cl.logged_at AT TIME ZONE :tz))::date AS week_start
        FROM consumption_log cl
        WHERE cl.action IN (:discard, :use_full)
          AND NOT (
              cl.action = :discard AND EXISTS (
                  SELECT 1 FROM consumption_log r
                  WHERE r.action = :restore
                    AND r.logged_at > cl.logged_at
                    AND (
                        r.inventory_item_id = cl.inventory_item_id
                        OR (
                            r.inventory_item_id IS NULL
                            AND cl.inventory_item_id IS NULL
                            AND r.product_master_id = cl.product_master_id
                            AND r.unit = cl.unit
                            AND r.quantity_consumed = cl.quantity_consumed
                        )
                    )
              )
          )
    )
    SELECT
        w.week_start,
        count(*) FILTER (WHERE c.action = :discard) AS discarded,
        count(*) FILTER (WHERE c.action = :use_full) AS finished
    FROM weeks w
    LEFT JOIN countable c ON c.week_start = w.week_start
    GROUP BY w.week_start
    ORDER BY w.week_start
    """
).bindparams(
    bindparam("now", type_=DateTime(timezone=True)),
    bindparam("tz", type_=String),
    bindparam("back", type_=Integer),
    bindparam("discard", type_=String),
    bindparam("use_full", type_=String),
    bindparam("restore", type_=String),
)


async def trend_figures(
    db: AsyncSession, *, weeks: int = TREND_WEEKS, now: datetime | None = None
) -> list[WeekFigures]:
    """The last `weeks` ISO weeks, oldest first, Europe/Helsinki. The window filter (`since`
    in `waste_figures`) never applies here - the trend always looks back from today.

    `now` is for tests; the endpoint leaves it at the real clock.
    """
    anchor = now or datetime.now(UTC)
    rows = (
        await db.execute(
            _TREND_SQL,
            {
                "now": anchor,
                "tz": TZ,
                "back": weeks - 1,
                "discard": _DISCARD,
                "use_full": _USE_FULL,
                "restore": _RESTORE,
            },
        )
    ).all()
    return [
        WeekFigures(
            week_start=row.week_start, discarded=row.discarded, finished=row.finished
        )
        for row in rows
    ]
