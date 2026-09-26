"""Q24: a date the cook corrects teaches the product its shelf life.

The estimate cannot see a printed date. Tortillas that keep until November were dated a week
out, every pack, because correcting one item taught the product nothing. The learning rule
reads the cook's recent dates off the product's own stock and stores what they imply the
same way a number typed on the Products screen is stored: `shelf_life_source = 'cook'`.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.shelf_life_learning import learn_shelf_life

BOUGHT = date(2026, 9, 1)


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


@pytest.fixture
async def tortillas(db_session: AsyncSession, categories) -> ProductMaster:
    product = ProductMaster(
        canonical_name="Tortillas",
        category="bread",
        storage_type="pantry",
        default_shelf_life_days=7,
        shelf_life_source="model",
        unit_type="count",
        default_unit="pcs",
    )
    db_session.add(product)
    await db_session.commit()
    return product


_seq = 0


def _item(product: ProductMaster, **kwargs) -> InventoryItem:
    """An item; each one created a second after the last, so ties on purchase break stably."""
    global _seq
    _seq += 1
    purchase = kwargs.pop("purchase_date", BOUGHT)
    days = kwargs.pop("days", 7)
    defaults = dict(
        product_master_id=product.id,
        initial_quantity=Decimal("8"),
        current_quantity=Decimal("8"),
        unit="pcs",
        status="sealed",
        purchase_date=purchase,
        expiry_date=(purchase or BOUGHT) + timedelta(days=days),
        expiry_source="manual",
        location="pantry",
        created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=_seq),
    )
    return InventoryItem(**{**defaults, **kwargs})


async def _add(db: AsyncSession, *items: InventoryItem) -> None:
    db.add_all(items)
    await db.commit()


async def _learn(db: AsyncSession, product: ProductMaster):
    learned = await learn_shelf_life(db, product.id)
    await db.commit()
    await db.refresh(product)
    return learned


class TestWhatIsLearned:
    async def test_one_observation_is_enough(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(db_session, _item(tortillas, days=60))

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert (learned.old_days, learned.new_days) == (7, 60)
        assert learned.observations == 1
        assert tortillas.default_shelf_life_days == 60

    async def test_the_learned_number_is_the_cooks(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        """Stored exactly like a number typed on the Products screen, so no estimate
        may overwrite it (operator ruling, 2026-09-26)."""
        await _add(db_session, _item(tortillas, days=60))

        await _learn(db_session, tortillas)

        assert tortillas.shelf_life_source == "cook"

    async def test_the_median_ignores_one_odd_pack(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(
            db_session,
            *[
                _item(tortillas, days=days, purchase_date=BOUGHT + timedelta(days=i))
                for i, days in enumerate([58, 60, 200, 61, 59])
            ],
        )

        await _learn(db_session, tortillas)

        assert tortillas.default_shelf_life_days == 60

    async def test_with_two_the_most_recent_wins(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        """An older row implying 3 days must not hold back a correction to +60."""
        await _add(
            db_session,
            _item(tortillas, days=3, purchase_date=BOUGHT),
            _item(tortillas, days=60, purchase_date=BOUGHT + timedelta(days=1)),
        )

        await _learn(db_session, tortillas)

        assert tortillas.default_shelf_life_days == 60

    async def test_with_two_the_most_recent_wins_downwards_too(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(
            db_session,
            _item(tortillas, days=60, purchase_date=BOUGHT),
            _item(tortillas, days=40, purchase_date=BOUGHT + timedelta(days=1)),
        )

        await _learn(db_session, tortillas)

        assert tortillas.default_shelf_life_days == 40

    async def test_with_two_bought_the_same_day_the_later_created_wins(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(db_session, _item(tortillas, days=60), _item(tortillas, days=45))

        await _learn(db_session, tortillas)

        assert tortillas.default_shelf_life_days == 45

    async def test_three_take_the_median(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(
            db_session,
            *[
                _item(tortillas, days=days, purchase_date=BOUGHT + timedelta(days=i))
                for i, days in enumerate([60, 3, 50])
            ],
        )

        await _learn(db_session, tortillas)

        assert tortillas.default_shelf_life_days == 50

    async def test_an_even_count_takes_the_mean_of_the_middle_two_rounded_half_up(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(
            db_session,
            *[
                _item(tortillas, days=days, purchase_date=BOUGHT + timedelta(days=i))
                for i, days in enumerate([10, 40, 20, 31])
            ],
        )

        await _learn(db_session, tortillas)

        # sorted 10, 20, 31, 40: (20 + 31) / 2 = 25.5 -> 26
        assert tortillas.default_shelf_life_days == 26

    async def test_only_the_last_five_count(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        """Old packs from a different supplier stop mattering once there are newer ones."""
        old = [
            _item(tortillas, days=10, purchase_date=BOUGHT - timedelta(days=100 + i))
            for i in range(5)
        ]
        new = [
            _item(tortillas, days=60, purchase_date=BOUGHT + timedelta(days=i))
            for i in range(5)
        ]
        await _add(db_session, *old, *new)

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert learned.observations == 5
        assert tortillas.default_shelf_life_days == 60

    async def test_ties_on_purchase_date_break_on_creation(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        """Six items bought the same day: the first one created is the one left out."""
        await _add(
            db_session,
            _item(tortillas, days=10),
            *[_item(tortillas, days=60) for _ in range(5)],
        )

        await _learn(db_session, tortillas)

        assert tortillas.default_shelf_life_days == 60

    async def test_used_up_and_discarded_items_still_count(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(
            db_session,
            _item(tortillas, days=60, status="empty", current_quantity=Decimal("0")),
            _item(tortillas, days=60, status="discarded"),
        )

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert learned.observations == 2
        assert tortillas.default_shelf_life_days == 60

    @pytest.mark.parametrize("days", [0, -3])
    async def test_an_expiry_on_or_before_purchase_is_ignored(
        self, db_session: AsyncSession, tortillas: ProductMaster, days: int
    ) -> None:
        """An "eat today" entry says nothing about how long a sealed pack keeps."""
        await _add(db_session, _item(tortillas, days=days))

        assert await _learn(db_session, tortillas) is None

        assert (tortillas.default_shelf_life_days, tortillas.shelf_life_source) == (
            7,
            "model",
        )

    async def test_an_ignored_date_does_not_take_a_recent_slot(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        """The newest row dated on its purchase day is skipped; the one before it wins."""
        await _add(
            db_session,
            _item(tortillas, days=60, purchase_date=BOUGHT),
            _item(tortillas, days=0, purchase_date=BOUGHT + timedelta(days=1)),
        )

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert learned.observations == 1
        assert tortillas.default_shelf_life_days == 60


class TestWhatIsNotAnObservation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"opened_date": BOUGHT + timedelta(days=2)}, id="opened"),
            pytest.param({"location": "freezer"}, id="frozen"),
            pytest.param({"purchase_date": None}, id="no-purchase-date"),
            pytest.param({"expiry_source": "calculated"}, id="calculated"),
            pytest.param({"expiry_source": "scanned"}, id="scanned"),
            pytest.param({"expiry_source": "frozen"}, id="frozen-source"),
        ],
    )
    async def test_it_is_ignored(
        self, db_session: AsyncSession, tortillas: ProductMaster, kwargs
    ) -> None:
        await _add(db_session, _item(tortillas, days=60, **kwargs))

        learned = await _learn(db_session, tortillas)

        assert learned is None
        assert (tortillas.default_shelf_life_days, tortillas.shelf_life_source) == (
            7,
            "model",
        )

    async def test_another_products_dates_do_not_count(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        other = ProductMaster(
            canonical_name="Cream",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="volume",
            default_unit="dl",
        )
        db_session.add(other)
        await db_session.commit()
        await _add(db_session, _item(other, days=42, unit="dl"))

        assert await _learn(db_session, tortillas) is None


class TestTheStockMovesWithIt:
    async def test_a_calculated_sibling_is_redated_and_a_manual_one_is_not(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        corrected = _item(tortillas, days=60)
        calculated = _item(
            tortillas,
            days=7,
            purchase_date=BOUGHT - timedelta(days=3),
            expiry_source="calculated",
        )
        typed = _item(
            tortillas,
            days=14,
            purchase_date=BOUGHT - timedelta(days=3),
            expiry_source="manual",
            # opened, so it is not an observation of its own - only a sibling
            opened_date=BOUGHT,
        )
        await _add(db_session, corrected, calculated, typed)

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert tortillas.default_shelf_life_days == 60
        await db_session.refresh(calculated)
        await db_session.refresh(typed)
        assert calculated.expiry_date == calculated.purchase_date + timedelta(days=60)
        assert typed.expiry_date == typed.purchase_date + timedelta(days=14)
        assert [m.id for m in learned.moved] == [calculated.id]


class TestNothingToLearn:
    async def test_no_observations_changes_nothing(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        calculated = _item(tortillas, days=3, expiry_source="calculated")
        await _add(db_session, calculated)

        assert await _learn(db_session, tortillas) is None

        await db_session.refresh(calculated)
        assert calculated.expiry_date == BOUGHT + timedelta(days=3)
        assert tortillas.shelf_life_source == "model"

    async def test_the_same_answer_again_changes_nothing_and_redates_nothing(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        await _add(db_session, _item(tortillas, days=60))
        assert await _learn(db_session, tortillas) is not None
        # A calculated item left off the new number: only a change may move it back
        stray = _item(tortillas, days=3, expiry_source="calculated")
        await _add(db_session, stray)

        assert await _learn(db_session, tortillas) is None

        await db_session.refresh(stray)
        assert stray.expiry_date == BOUGHT + timedelta(days=3)

    async def test_a_cook_number_differing_from_the_dates_is_replaced(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        tortillas.shelf_life_source = "cook"
        tortillas.default_shelf_life_days = 30
        await db_session.commit()
        await _add(db_session, _item(tortillas, days=60))

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert (learned.old_days, learned.new_days) == (30, 60)

    async def test_the_same_days_from_an_estimate_become_the_cooks(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        """The number is right but an estimate could still overwrite it: protect it."""
        await _add(db_session, _item(tortillas, days=7))

        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert (tortillas.default_shelf_life_days, tortillas.shelf_life_source) == (
            7,
            "cook",
        )


class TestReCorrecting:
    async def test_correcting_the_same_item_again_replaces_its_observation(
        self, db_session: AsyncSession, tortillas: ProductMaster
    ) -> None:
        item = _item(tortillas, days=30)
        await _add(db_session, item)
        await _learn(db_session, tortillas)
        assert tortillas.default_shelf_life_days == 30

        item.expiry_date = BOUGHT + timedelta(days=60)
        await db_session.commit()
        learned = await _learn(db_session, tortillas)

        assert learned is not None
        assert learned.observations == 1
        assert tortillas.default_shelf_life_days == 60
