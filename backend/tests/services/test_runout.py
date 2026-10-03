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
