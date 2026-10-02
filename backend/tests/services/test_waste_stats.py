"""waste_stats: the Gone screen's waste rate and 8-week trend (planner ruling, 2026-10-02).

Waste rate = discarded items / (discarded + finished items), counted by events because grams
and pieces do not add up (ActionSummary). A discard a later restore undid is not waste;
corrections, part-uses and restores stay out entirely, exactly as the Gone list leaves them.
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
from app.services import waste_stats

TODAY = date.today()


@pytest.fixture
async def db(db_session: AsyncSession) -> AsyncSession:
    await seed_categories(db_session)
    await db_session.commit()
    return db_session


async def _product(
    db: AsyncSession, name: str, *, category: str = "dairy"
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
    )
    db.add(product)
    await db.commit()
    return product


async def _item(db: AsyncSession, product: ProductMaster) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal("10"),
        current_quantity=Decimal("10"),
        unit="dl",
        status="sealed",
        expiry_date=TODAY + timedelta(days=7),
        location="main_fridge",
    )
    db.add(item)
    await db.commit()
    return item


async def _log(
    db: AsyncSession,
    item: InventoryItem,
    product: ProductMaster,
    action: str,
    *,
    logged_at: datetime,
) -> ConsumptionLog:
    log = ConsumptionLog(
        inventory_item_id=item.id,
        product_master_id=product.id,
        action=action,
        quantity_consumed=Decimal("1"),
        quantity_after=Decimal("0") if action == "discard" else Decimal("1"),
        unit="dl",
        batch_id=uuid4(),
        previous={},
        logged_at=logged_at,
    )
    db.add(log)
    await db.commit()
    return log


class TestWasteFigures:
    async def test_the_rate_is_discarded_over_discarded_and_finished(
        self, db: AsyncSession
    ) -> None:
        product = await _product(db, "Milk")
        now = datetime.now(UTC)
        for action in ("discard", "discard", "use_full"):
            item = await _item(db, product)
            await _log(db, item, product, action, logged_at=now)

        figures = await waste_stats.waste_figures(db)

        assert (figures.discarded, figures.finished, figures.total) == (2, 1, 3)
        assert figures.rate == pytest.approx(2 / 3)

    async def test_corrections_part_uses_and_restores_do_not_count(
        self, db: AsyncSession
    ) -> None:
        product = await _product(db, "Milk")
        now = datetime.now(UTC)
        item = await _item(db, product)
        await _log(db, item, product, "discard", logged_at=now)
        for action in ("use_partial", "correct", "restore"):
            other = await _item(db, product)
            await _log(db, other, product, action, logged_at=now)

        figures = await waste_stats.waste_figures(db)

        assert (figures.discarded, figures.finished, figures.total) == (1, 0, 1)

    async def test_a_restored_discard_is_not_waste(self, db: AsyncSession) -> None:
        product = await _product(db, "Milk")
        item = await _item(db, product)
        discarded_at = datetime.now(UTC) - timedelta(hours=1)
        await _log(db, item, product, "discard", logged_at=discarded_at)
        await _log(
            db, item, product, "restore", logged_at=discarded_at + timedelta(minutes=5)
        )

        figures = await waste_stats.waste_figures(db)

        assert (figures.discarded, figures.finished, figures.total) == (0, 0, 0)
        assert figures.rate is None

    async def test_an_unrestored_discard_still_counts(self, db: AsyncSession) -> None:
        """A restore on a *different* item must not clear this one's discard."""
        product = await _product(db, "Milk")
        binned = await _item(db, product)
        other = await _item(db, product)
        now = datetime.now(UTC)
        await _log(db, binned, product, "discard", logged_at=now - timedelta(hours=1))
        await _log(db, other, product, "restore", logged_at=now)

        figures = await waste_stats.waste_figures(db)

        assert figures.discarded == 1

    async def test_since_bounds_the_window(self, db: AsyncSession) -> None:
        product = await _product(db, "Milk")
        old_item = await _item(db, product)
        new_item = await _item(db, product)
        now = datetime.now(UTC)
        old = now - timedelta(days=10)
        new = now - timedelta(hours=1)
        await _log(db, old_item, product, "discard", logged_at=old)
        await _log(db, new_item, product, "discard", logged_at=new)

        figures = await waste_stats.waste_figures(db, since=new - timedelta(minutes=1))

        assert figures.discarded == 1

    async def test_an_empty_window_has_no_rate_and_no_categories(
        self, db: AsyncSession
    ) -> None:
        figures = await waste_stats.waste_figures(db)

        assert figures.total == 0
        assert figures.rate is None
        assert figures.categories == []


class TestCategoryBreakdown:
    async def test_a_category_under_three_events_does_not_appear(
        self, db: AsyncSession
    ) -> None:
        dairy = await _product(db, "Milk", category="dairy")
        meat = await _product(db, "Mince", category="meat")
        now = datetime.now(UTC)
        for _ in range(2):
            item = await _item(db, dairy)
            await _log(db, item, dairy, "discard", logged_at=now)
        item = await _item(db, meat)
        await _log(db, item, meat, "discard", logged_at=now)

        figures = await waste_stats.waste_figures(db)

        assert figures.categories == []

    async def test_the_worst_category_comes_first(self, db: AsyncSession) -> None:
        dairy = await _product(db, "Milk", category="dairy")
        meat = await _product(db, "Mince", category="meat")
        now = datetime.now(UTC)
        for action in ("discard", "use_full", "use_full"):
            item = await _item(db, dairy)
            await _log(db, item, dairy, action, logged_at=now)
        for _ in range(3):
            item = await _item(db, meat)
            await _log(db, item, meat, "discard", logged_at=now)

        figures = await waste_stats.waste_figures(db)

        assert [c.category for c in figures.categories] == ["meat", "dairy"]
        assert figures.categories[0].rate == 1.0
        assert figures.categories[0].display_name == "Meat & Poultry"
        assert figures.categories[1].rate == pytest.approx(1 / 3)

    async def test_a_restored_discard_does_not_count_toward_the_category_either(
        self, db: AsyncSession
    ) -> None:
        meat = await _product(db, "Mince", category="meat")
        now = datetime.now(UTC)
        for _ in range(2):
            item = await _item(db, meat)
            await _log(db, item, meat, "use_full", logged_at=now)
        restored = await _item(db, meat)
        await _log(db, restored, meat, "discard", logged_at=now - timedelta(minutes=10))
        await _log(db, restored, meat, "restore", logged_at=now - timedelta(minutes=5))

        figures = await waste_stats.waste_figures(db)

        # Only the two use_full events are countable, so the category misses the threshold.
        assert figures.categories == []


class TestTrend:
    async def test_eight_weeks_ending_with_the_current_one(
        self, db: AsyncSession
    ) -> None:
        now = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)  # a Wednesday, Helsinki local

        weeks = await waste_stats.trend_figures(db, now=now)

        assert len(weeks) == 8
        assert weeks[-1].week_start == date(
            2026, 1, 19
        )  # the Monday of now's local week
        assert weeks[0].week_start == date(2025, 12, 1)
        assert all(w.total == 0 and w.rate is None for w in weeks)

    async def test_an_event_lands_in_its_own_week(self, db: AsyncSession) -> None:
        product = await _product(db, "Milk")
        item = await _item(db, product)
        now = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)
        await _log(
            db,
            item,
            product,
            "discard",
            logged_at=datetime(2026, 1, 20, 10, 0, tzinfo=UTC),
        )

        weeks = await waste_stats.trend_figures(db, now=now)

        by_week = {w.week_start: w for w in weeks}
        assert by_week[date(2026, 1, 19)].discarded == 1
        assert by_week[date(2026, 1, 19)].rate == 1.0

    async def test_a_late_sunday_event_stays_in_its_own_week_not_the_next(
        self, db: AsyncSession
    ) -> None:
        """Europe/Helsinki, winter (UTC+2). 2026-01-18 is a Sunday there.

        Sunday 2026-01-18 23:30 local is 21:30 UTC *that same day* - it belongs to the week
        of 2026-01-12. Monday 2026-01-19 00:05 local is 22:05 UTC the day before - the same
        UTC calendar day as the first event - yet it already belongs to the next week,
        2026-01-19. Binning in UTC instead of Europe/Helsinki would merge the two.
        """
        product = await _product(db, "Milk")
        sunday_item = await _item(db, product)
        monday_item = await _item(db, product)
        sunday_23_30_local = datetime(2026, 1, 18, 21, 30, tzinfo=UTC)
        monday_00_05_local = datetime(2026, 1, 18, 22, 5, tzinfo=UTC)
        await _log(db, sunday_item, product, "discard", logged_at=sunday_23_30_local)
        await _log(db, monday_item, product, "discard", logged_at=monday_00_05_local)

        now = datetime(2026, 1, 25, 12, 0, tzinfo=UTC)
        weeks = await waste_stats.trend_figures(db, now=now)
        by_week = {w.week_start: w for w in weeks}

        assert by_week[date(2026, 1, 12)].discarded == 1
        assert by_week[date(2026, 1, 19)].discarded == 1

    async def test_the_window_filter_does_not_apply_to_the_trend(
        self, db: AsyncSession
    ) -> None:
        """`since` narrows `waste_figures`; the trend always looks back 8 weeks regardless."""
        product = await _product(db, "Milk")
        item = await _item(db, product)
        now = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)
        await _log(
            db,
            item,
            product,
            "discard",
            logged_at=datetime(2025, 12, 5, 10, 0, tzinfo=UTC),
        )

        weeks = await waste_stats.trend_figures(db, now=now)

        assert sum(w.discarded for w in weeks) == 1

    async def test_a_restored_discard_is_excluded_from_the_trend_too(
        self, db: AsyncSession
    ) -> None:
        product = await _product(db, "Milk")
        item = await _item(db, product)
        now = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)
        discarded_at = datetime(2026, 1, 20, 10, 0, tzinfo=UTC)
        await _log(db, item, product, "discard", logged_at=discarded_at)
        await _log(
            db, item, product, "restore", logged_at=discarded_at + timedelta(minutes=5)
        )

        weeks = await waste_stats.trend_figures(db, now=now)

        assert all(w.discarded == 0 for w in weeks)
