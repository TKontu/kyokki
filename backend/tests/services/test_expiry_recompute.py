"""A shelf-life correction reaches the food (Q12).

Q11 gave the catalog two ways to change its mind about a shelf life and neither touched
stock, so `HANDOFF.md`'s own recipe - confirm a receipt, then run the estimate - left the
mince in the fridge claiming the number the estimate had just replaced.

What must *not* move matters as much as what must: a date the cook typed, a barcode's date,
an item already gone, and - the subtle one - an opened item that would gain time.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.expiry_recompute import (
    recompute_expiry_for_product,
    recomputed_expiry,
    sealed_expiry,
)

PURCHASED = date(2026, 9, 1)


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


def _product(**kwargs) -> ProductMaster:
    defaults = dict(
        canonical_name="Ground beef",
        category="meat",
        storage_type="refrigerator",
        default_shelf_life_days=5,
        unit_type="weight",
        default_unit="g",
    )
    return ProductMaster(**{**defaults, **kwargs})


def _item(**kwargs) -> InventoryItem:
    defaults = dict(
        initial_quantity=Decimal("400"),
        current_quantity=Decimal("400"),
        unit="g",
        status="sealed",
        purchase_date=PURCHASED,
        expiry_date=PURCHASED + timedelta(days=5),
        expiry_source="calculated",
        location="main_fridge",
    )
    return InventoryItem(**{**defaults, **kwargs})


class TestSealedExpiry:
    def test_it_is_the_formula_confirm_has_always_used(self) -> None:
        assert sealed_expiry(_product(), PURCHASED) == date(2026, 9, 6)


class TestRecomputedExpiry:
    """The decision, without a database in the way."""

    def test_a_shorter_shelf_life_pulls_the_date_in(self) -> None:
        product = _product(default_shelf_life_days=2)

        assert recomputed_expiry(_item(), product) == date(2026, 9, 3)

    def test_a_longer_shelf_life_pushes_it_out(self) -> None:
        """A sealed pack that keeps longer than we thought really does keep longer."""
        product = _product(default_shelf_life_days=30)

        assert recomputed_expiry(_item(), product) == date(2026, 10, 1)

    @pytest.mark.parametrize("source", ["manual", "scanned"])
    def test_a_date_somebody_chose_is_never_touched(self, source) -> None:
        """The mirror of Q11's `shelf_life_source == 'cook'`."""
        item = _item(expiry_source=source, expiry_date=date(2026, 12, 24))

        assert recomputed_expiry(item, _product(default_shelf_life_days=2)) is None

    def test_without_a_purchase_date_there_is_nothing_to_count_from(self) -> None:
        """`purchase_date` is nullable, and a hand-added item may have none."""
        assert recomputed_expiry(_item(purchase_date=None), _product()) is None

    def test_an_opened_item_is_capped_by_its_opened_clock(self) -> None:
        """Q5's invariant: opening may only ever shorten.

        Without the cap, correcting this product's shelf life upwards would hand an opened
        tub back the fortnight that opening it took away.
        """
        product = _product(
            canonical_name="Sour cream",
            default_shelf_life_days=30,
            opened_shelf_life_days=5,
        )
        opened = _item(
            status="opened",
            opened_date=date(2026, 9, 10),
            expiry_date=date(2026, 9, 15),
        )

        # sealed would say 1 October; the opened clock says 15 September and wins
        assert recomputed_expiry(opened, product) == date(2026, 9, 15)

    def test_an_opened_item_still_shortens_when_the_sealed_life_is_shorter(
        self,
    ) -> None:
        product = _product(default_shelf_life_days=2, opened_shelf_life_days=30)
        opened = _item(status="opened", opened_date=date(2026, 9, 10))

        assert recomputed_expiry(opened, product) == date(2026, 9, 3)

    def test_loose_produce_has_no_opened_clock_to_respect(self) -> None:
        """Taking one apple from the bowl never opened anything.

        `_start_opened_clock` exempts anything with a piece weight, so there is no opened
        date to cap against even when one is stored.
        """
        product = _product(
            canonical_name="Apple",
            default_shelf_life_days=30,
            opened_shelf_life_days=2,
            avg_piece_grams=Decimal("125"),
        )
        item = _item(status="partial", opened_date=date(2026, 9, 10))

        assert recomputed_expiry(item, product) == date(2026, 10, 1)


class TestRecomputeExpiryForProduct:
    """The write path, against the database."""

    async def _stocked(
        self, db_session: AsyncSession, product: ProductMaster, **item_kwargs
    ) -> InventoryItem:
        db_session.add(product)
        await db_session.flush()
        item = _item(product_master_id=product.id, **item_kwargs)
        db_session.add(item)
        await db_session.flush()
        return item

    async def test_it_moves_the_stock_and_says_which(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = _product()
        item = await self._stocked(db_session, product)
        product.default_shelf_life_days = 2

        moved = await recompute_expiry_for_product(db_session, product)

        assert [m.id for m in moved] == [item.id]
        assert item.expiry_date == date(2026, 9, 3)

    async def test_an_unchanged_date_is_not_a_move(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Re-running a refresh should report nothing rather than churn."""
        product = _product()
        await self._stocked(db_session, product)

        assert await recompute_expiry_for_product(db_session, product) == []

    @pytest.mark.parametrize("status", ["empty", "discarded"])
    async def test_food_already_gone_is_left_alone(
        self, db_session: AsyncSession, categories, status
    ) -> None:
        product = _product()
        item = await self._stocked(
            db_session, product, status=status, current_quantity=Decimal("0")
        )
        product.default_shelf_life_days = 2

        assert await recompute_expiry_for_product(db_session, product) == []
        assert item.expiry_date == PURCHASED + timedelta(days=5)

    async def test_a_hand_typed_date_survives(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = _product()
        item = await self._stocked(
            db_session, product, expiry_source="manual", expiry_date=date(2026, 12, 24)
        )
        product.default_shelf_life_days = 2

        assert await recompute_expiry_for_product(db_session, product) == []
        assert item.expiry_date == date(2026, 12, 24)

    async def test_only_this_product_s_stock_moves(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = _product()
        other = _product(canonical_name="Ham")
        mine = await self._stocked(db_session, product)
        theirs = await self._stocked(db_session, other)
        product.default_shelf_life_days = 2

        moved = await recompute_expiry_for_product(db_session, product)

        assert [m.id for m in moved] == [mine.id]
        assert theirs.expiry_date == PURCHASED + timedelta(days=5)

    async def test_a_product_with_no_stock_is_no_work(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = _product()
        db_session.add(product)
        await db_session.flush()
        product.default_shelf_life_days = 2

        assert await recompute_expiry_for_product(db_session, product) == []
