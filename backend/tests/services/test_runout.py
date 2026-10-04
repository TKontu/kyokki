"""services.runout: a daily use rate from `consumption_log`, and when active stock runs
out (Phase 3 "Consumption Learning", frontier item 8, docs/TODO.md). See the module's
own docstring for the method - it is deliberately simple, with no seasonality; these
tests pin its arithmetic.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services import runout

# A fixed anchor (not "now"), so the Europe/Helsinki day it falls on never depends on
# when the suite runs or daylight saving.
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
TODAY: date = runout._today(NOW)


@pytest.fixture
async def db(db_session: AsyncSession) -> AsyncSession:
    await seed_categories(db_session)
    await db_session.commit()
    return db_session


async def _product(
    db: AsyncSession,
    name: str,
    *,
    unit: str = "dl",
    category: str = "dairy",
) -> ProductMaster:
    unit_type = {"dl": "volume", "g": "weight", "pcs": "count", "tsp": "volume"}[unit]
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type=unit_type,
        default_unit=unit,
    )
    db.add(product)
    await db.commit()
    return product


async def _item(
    db: AsyncSession,
    product: ProductMaster,
    quantity: str,
    *,
    unit: str = "dl",
    expires_in: int = 30,
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(quantity),
        current_quantity=Decimal(quantity),
        unit=unit,
        status="sealed",
        expiry_date=TODAY + timedelta(days=expires_in),
        location="main_fridge",
    )
    db.add(item)
    await db.commit()
    return item


async def _log(
    db: AsyncSession,
    product: ProductMaster,
    action: str,
    *,
    days_ago: int,
    quantity: str,
    unit: str = "dl",
) -> ConsumptionLog:
    log = ConsumptionLog(
        inventory_item_id=None,
        product_master_id=product.id,
        action=action,
        quantity_consumed=Decimal(quantity),
        quantity_after=Decimal("0"),
        unit=unit,
        batch_id=uuid4(),
        previous={},
        logged_at=NOW - timedelta(days=days_ago),
    )
    db.add(log)
    await db.commit()
    return log


async def _one(db: AsyncSession, product_id, **kwargs) -> runout.RunoutProduct:
    results = await runout.forecast(db, now=NOW, **kwargs)
    return next(r for r in results if r.product_id == product_id)


class TestRateMaths:
    async def test_steady_use_forecasts_days_left(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5")
        # 5 events, 2 dl each, 2 days apart: first 8 days ago, span 8 days (no floor).
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        result = await _one(db, milk.id)

        assert result.status == "forecast"
        assert result.daily_rate == Decimal("1.25")  # 10 dl / 8 days
        assert result.days_left == 4  # 5 dl / 1.25 dl/day
        assert result.runs_out_on == TODAY + timedelta(days=4)
        assert result.expires_first is False

    async def test_minimum_span_floors_a_short_history(self, db: AsyncSession) -> None:
        eggs = await _product(db, "Eggs", unit="pcs")
        await _item(db, eggs, "14", unit="pcs")
        # 3 events over 2 real days; the window used must floor to 7 days, not 2.
        for days_ago in (2, 1, 0):
            await _log(
                db, eggs, "use_full", days_ago=days_ago, quantity="1", unit="pcs"
            )

        result = await _one(db, eggs.id)

        assert result.status == "forecast"
        # 3 pcs / 7 days (floored from the real 2-day span), quantised to cents.
        assert result.daily_rate == Decimal("0.43")

    async def test_a_burst_on_one_day_is_insufficient_history(
        self, db: AsyncSession
    ) -> None:
        rice = await _product(db, "Rice", unit="g")
        await _item(db, rice, "500", unit="g")
        # Five events, but all logged the same day: only 1 distinct day, short of the
        # 2 required, however many events there were.
        for _ in range(5):
            await _log(db, rice, "use_partial", days_ago=0, quantity="10", unit="g")

        result = await _one(db, rice.id)

        assert result.status == "insufficient_history"
        assert result.daily_rate is None
        assert result.runs_out_on is None
        assert result.days_left is None

    async def test_discards_do_not_count_toward_the_rate(
        self, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")
        # A big discard, logged in the same window: waste, not use.
        await _log(db, milk, "discard", days_ago=3, quantity="50")

        result = await _one(db, milk.id)

        assert result.daily_rate == Decimal("1.25")

    async def test_undone_rows_are_excluded(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")
        # A sixth event that was then undone: the general undo (services.undo)
        # deletes the row outright, not marks it - simulate that directly.
        undone = await _log(db, milk, "use_partial", days_ago=1, quantity="100")
        await db.delete(undone)
        await db.commit()

        result = await _one(db, milk.id)

        assert result.daily_rate == Decimal("1.25")

    async def test_unit_conversion(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5")
        # Logged in dl and in ml; both must land in the product's own dl.
        for days_ago in (8, 6, 4):
            await _log(
                db, milk, "use_partial", days_ago=days_ago, quantity="2", unit="dl"
            )
        for days_ago in (2, 0):
            await _log(
                db, milk, "use_partial", days_ago=days_ago, quantity="200", unit="ml"
            )

        result = await _one(db, milk.id)

        # 3 * 2 dl + 2 * 2 dl (200 ml == 2 dl) = 10 dl over 8 days.
        assert result.daily_rate == Decimal("1.25")

    async def test_short_history_is_insufficient(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5")
        for days_ago in (4, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        result = await _one(db, milk.id)

        assert result.status == "insufficient_history"
        assert result.daily_rate is None
        assert result.runs_out_on is None
        assert result.days_left is None


class TestRunOutDate:
    async def test_zero_stock_is_out(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        # Enough history, but nothing left in the kitchen - no item at all.
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        result = await _one(db, milk.id, include_out=True)

        assert result.status == "out"
        assert result.active_stock == Decimal("0.00")
        assert result.runs_out_on is None
        assert result.days_left == 0

    async def test_vanishing_rate_has_no_runs_out_on(self, db: AsyncSession) -> None:
        tea = await _product(db, "Tea", unit="g")
        await _item(db, tea, "500", unit="g")
        # Enough history (3 events, 2 distinct days), but so little of it that the
        # quantised rate rounds to 0 - a forecast with no end in sight.
        for days_ago in (6, 3, 0):
            await _log(
                db, tea, "use_partial", days_ago=days_ago, quantity="0.01", unit="g"
            )

        result = await _one(db, tea.id)

        assert result.status == "forecast"
        assert result.daily_rate == Decimal("0.00")
        assert result.runs_out_on is None
        assert result.days_left is None


class TestExpiresFirst:
    async def test_flagged_when_expiry_is_before_the_run_out_date(
        self, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5", expires_in=2)  # runs out in 4 days (below)
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        result = await _one(db, milk.id)

        assert result.runs_out_on == TODAY + timedelta(days=4)
        assert result.expires_first is True

    async def test_not_flagged_when_expiry_is_after_the_run_out_date(
        self, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk", unit="dl")
        await _item(db, milk, "5", expires_in=30)
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        result = await _one(db, milk.id)

        assert result.expires_first is False


class TestWithinDaysFilter:
    async def test_filters_to_days_left_at_or_under_n(self, db: AsyncSession) -> None:
        soon = await _product(db, "Soon", unit="dl")
        await _item(db, soon, "2")  # 2 dl / 1.25 dl/day ~ 2 days
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, soon, "use_partial", days_ago=days_ago, quantity="2")

        later = await _product(db, "Later", unit="dl")
        await _item(db, later, "100")  # far more stock, same rate -> many days left
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, later, "use_partial", days_ago=days_ago, quantity="2")

        short_history = await _product(db, "ShortHistory", unit="dl")
        await _item(db, short_history, "5")
        for days_ago in (4, 0):
            await _log(
                db, short_history, "use_partial", days_ago=days_ago, quantity="2"
            )

        unfiltered = await runout.forecast(db, now=NOW)
        filtered = await runout.forecast(db, now=NOW, within_days=3)

        ids_unfiltered = {r.product_id for r in unfiltered}
        ids_filtered = {r.product_id for r in filtered}
        assert {soon.id, later.id, short_history.id} <= ids_unfiltered
        assert soon.id in ids_filtered
        assert later.id not in ids_filtered
        # insufficient_history has no days_left to compare, so the filter leaves it out.
        assert short_history.id not in ids_filtered


class TestIncludeOut:
    """``out`` items are dropped unless ``include_out`` is set (the production
    finding: products already out drown out the real forecasts otherwise)."""

    async def test_default_excludes_out(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        results = await runout.forecast(db, now=NOW)

        assert milk.id not in {r.product_id for r in results}

    async def test_include_out_includes_it(self, db: AsyncSession) -> None:
        milk = await _product(db, "Milk", unit="dl")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        results = await runout.forecast(db, now=NOW, include_out=True)

        result = next(r for r in results if r.product_id == milk.id)
        assert result.status == "out"

    async def test_within_days_still_excludes_out_by_default(
        self, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk", unit="dl")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        results = await runout.forecast(db, now=NOW, within_days=7)

        assert milk.id not in {r.product_id for r in results}

    async def test_within_days_with_include_out_lists_it(
        self, db: AsyncSession
    ) -> None:
        milk = await _product(db, "Milk", unit="dl")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        results = await runout.forecast(db, now=NOW, within_days=7, include_out=True)

        result = next(r for r in results if r.product_id == milk.id)
        assert result.status == "out"

    async def test_production_shape_default_holds_only_the_forecast(
        self, db: AsyncSession
    ) -> None:
        """28 products already out, one real forecast within 7 days: the default
        list (within_days=7) must hold exactly the forecast."""
        out_ids = set()
        for i in range(28):
            product = await _product(db, f"Out {i}", unit="dl")
            await _log(db, product, "use_partial", days_ago=2, quantity="1")
            await _log(db, product, "use_partial", days_ago=1, quantity="1")
            await _log(db, product, "use_partial", days_ago=0, quantity="1")
            out_ids.add(product.id)

        # Same pinned rate as TestRateMaths.test_steady_use_forecasts_days_left
        # (1.25 dl/day), with enough stock for 7 days rather than 4.
        rye = await _product(db, "Rye crispbread", unit="dl")
        await _item(db, rye, "9")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, rye, "use_partial", days_ago=days_ago, quantity="2")

        results = await runout.forecast(db, now=NOW, within_days=7)

        ids = {r.product_id for r in results}
        assert ids == {rye.id}
        assert not (ids & out_ids)

        with_out = await runout.forecast(db, now=NOW, within_days=7, include_out=True)
        assert {r.product_id for r in with_out} == out_ids | {rye.id}


class TestSorting:
    async def test_soonest_first(self, db: AsyncSession) -> None:
        slow = await _product(db, "Slow", unit="dl")
        await _item(db, slow, "100")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, slow, "use_partial", days_ago=days_ago, quantity="2")

        fast = await _product(db, "Fast", unit="dl")
        await _item(db, fast, "2")
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, fast, "use_partial", days_ago=days_ago, quantity="2")

        results = await runout.forecast(db, now=NOW)
        ordered_ids = [r.product_id for r in results]

        assert ordered_ids.index(fast.id) < ordered_ids.index(slow.id)


# --- In-stock days (#165 follow-up): days with nothing in stock do not dilute the rate ---


def _at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


async def _held_item(
    db: AsyncSession,
    product: ProductMaster,
    quantity: str,
    *,
    created_days_ago: float,
    status: str = "sealed",
    consumed_days_ago: float | None = None,
    unit: str = "dl",
) -> InventoryItem:
    """An item with an explicit history: entered ``created_days_ago``, and - for an
    ``empty`` or ``discarded`` one - left ``consumed_days_ago``."""
    gone = status in ("empty", "discarded")
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(quantity),
        current_quantity=Decimal("0") if status == "empty" else Decimal(quantity),
        unit=unit,
        status=status,
        expiry_date=TODAY + timedelta(days=30),
        location="main_fridge",
        created_at=_at(created_days_ago),
        consumed_at=(
            _at(consumed_days_ago) if gone and consumed_days_ago is not None else None
        ),
    )
    db.add(item)
    await db.commit()
    return item


async def _item_log(
    db: AsyncSession,
    item: InventoryItem,
    action: str,
    *,
    days_ago: float,
    quantity: str,
) -> ConsumptionLog:
    log = ConsumptionLog(
        inventory_item_id=item.id,
        product_master_id=item.product_master_id,
        action=action,
        quantity_consumed=Decimal(quantity),
        quantity_after=Decimal("0"),
        unit=str(item.unit),
        batch_id=uuid4(),
        previous={},
        logged_at=_at(days_ago),
    )
    db.add(log)
    await db.commit()
    return log


class TestInStockDays:
    async def test_out_of_stock_gap_does_not_dilute_the_rate(
        self, db: AsyncSession
    ) -> None:
        """Milk used daily from day 0 to day 10, out of stock for 30 days, restocked on
        day 40; today is day 42."""
        milk = await _product(db, "Milk", unit="dl")
        # The first carton: in from day 0 (an hour before the first use), empty on day 10.
        await _held_item(
            db,
            milk,
            "11",
            created_days_ago=42 + 1 / 24,
            status="empty",
            consumed_days_ago=32 - 1 / 24,
        )
        # The restock on day 40, still in the fridge.
        await _held_item(db, milk, "5", created_days_ago=2 + 1 / 24)
        for day in [*range(0, 11), 40, 41, 42]:
            await _log(db, milk, "use_partial", days_ago=42 - day, quantity="1")

        result = await _one(db, milk.id)

        # 14 dl over the in-stock days from day 0 up to today: days 0-10 (11) and
        # days 40-41 (2) = 13, not the 42 the calendar spans.
        assert result.status == "forecast"
        assert result.daily_rate == Decimal("1.08")  # 14 / 13
        assert result.days_left == 5  # 5 dl / 1.08 dl/day = 4.6
        assert result.runs_out_on == TODAY + timedelta(days=5)

    async def test_in_stock_but_unused_still_dilutes(self, db: AsyncSession) -> None:
        """The same use pattern, but the carton never ran out: the 30 quiet days are
        real low use and still count."""
        milk = await _product(db, "Milk", unit="dl")
        await _held_item(db, milk, "5", created_days_ago=42 + 1 / 24)
        for day in [*range(0, 11), 40, 41, 42]:
            await _log(db, milk, "use_partial", days_ago=42 - day, quantity="1")

        result = await _one(db, milk.id)

        assert result.status == "forecast"
        assert result.daily_rate == Decimal("0.33")  # 14 / 42
        assert result.days_left == 15  # 5 / 0.33 = 15.2
        assert result.runs_out_on == TODAY + timedelta(days=15)

    async def test_a_restored_item_is_in_stock_again_from_the_restore(
        self, db: AsyncSession
    ) -> None:
        """Bought on day 0, used to day 5, thrown away on day 5, restored on day 35 (the
        discard was a mis-tap noticed late); today is day 40."""
        jam = await _product(db, "Jam", unit="dl")
        item = await _held_item(db, jam, "10", created_days_ago=40 + 1 / 24)
        await _item_log(db, item, "discard", days_ago=35 - 2 / 24, quantity="10")
        await _item_log(db, item, "restore", days_ago=5 + 1 / 24, quantity="10")
        for day in [*range(0, 6), *range(35, 41)]:
            await _log(db, jam, "use_partial", days_ago=40 - day, quantity="1")

        result = await _one(db, jam.id)

        # 12 dl over days 0-5 (6) and days 35-39 (5) = 11 in-stock days.
        assert result.status == "forecast"
        assert result.daily_rate == Decimal("1.09")  # 12 / 11

    async def test_a_discarded_item_leaves_stock(self, db: AsyncSession) -> None:
        """A discard ends the item's time in stock just as running empty does."""
        jam = await _product(db, "Jam", unit="dl")
        old = await _held_item(
            db,
            jam,
            "10",
            created_days_ago=40 + 1 / 24,
            status="discarded",
            consumed_days_ago=35 - 2 / 24,
        )
        await _item_log(db, old, "discard", days_ago=35 - 2 / 24, quantity="10")
        await _held_item(db, jam, "10", created_days_ago=5 + 1 / 24)
        for day in [*range(0, 6), *range(35, 41)]:
            await _log(db, jam, "use_partial", days_ago=40 - day, quantity="1")

        result = await _one(db, jam.id)

        assert result.daily_rate == Decimal("1.09")  # 12 / 11

    async def test_falls_back_when_consume_events_predate_every_item(
        self, db: AsyncSession
    ) -> None:
        """Uses logged before any item that could have held them (older data): the
        history cannot be reconstructed, so the span is the plain calendar one."""
        milk = await _product(db, "Milk", unit="dl")
        await _held_item(db, milk, "5", created_days_ago=2 + 1 / 24)
        for days_ago in (8, 6, 4, 2, 0):
            await _log(db, milk, "use_partial", days_ago=days_ago, quantity="2")

        result = await _one(db, milk.id)

        # 10 dl / 8 calendar days, not 10 dl over the 2 days the item has been in.
        assert result.daily_rate == Decimal("1.25")
        assert result.days_left == 4


class TestQueryCount:
    async def _seed(self, db: AsyncSession, count: int) -> None:
        for i in range(count):
            product = await _product(db, f"Product {count}-{i}", unit="dl")
            gone = await _held_item(
                db,
                product,
                "4",
                created_days_ago=20,
                status="discarded",
                consumed_days_ago=12,
            )
            await _item_log(db, gone, "discard", days_ago=12, quantity="4")
            await _held_item(db, product, "5", created_days_ago=6)
            for days_ago in (19, 15, 5, 3, 1):
                await _log(db, product, "use_partial", days_ago=days_ago, quantity="1")

    async def _statements(self, db: AsyncSession) -> tuple[int, int]:
        from sqlalchemy import event

        statements: list[str] = []
        engine = db.bind.sync_engine

        def count(conn, cursor, statement, *args) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            results = await runout.forecast(db, now=NOW)
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(statements), len(results)

    async def test_same_statement_count_for_3_and_12_products(
        self, db: AsyncSession
    ) -> None:
        await self._seed(db, 3)
        three, reported_three = await self._statements(db)
        await self._seed(db, 9)
        twelve, reported_twelve = await self._statements(db)

        assert reported_three == 3
        assert reported_twelve == 12
        assert three == twelve
