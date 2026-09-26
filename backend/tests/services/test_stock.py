"""AG2: stock per product, and consume by name across items (services/stock.py)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.store_product_alias import StoreProductAlias
from app.schemas.stock import StockConsumeRequest
from app.services import stock
from app.services.product_lookup import AmbiguousProduct, ProductNotFound

TODAY = date.today()


@pytest.fixture
async def db(db_session: AsyncSession) -> AsyncSession:
    await seed_categories(db_session)
    await db_session.commit()
    return db_session


def _id(obj):
    """The row's id without loading it: a rolled-back session has expired every object."""
    return inspect(obj).identity[0]


async def _product(
    db: AsyncSession,
    name: str,
    *,
    unit: str = "dl",
    category: str = "dairy",
) -> ProductMaster:
    unit_type = {"dl": "volume", "g": "weight", "pcs": "count"}[unit]
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
    db.add(
        ProductName(
            product_master_id=product.id, name=name.casefold(), source="canonical"
        )
    )
    await db.commit()
    return product


async def _item(
    db: AsyncSession,
    product: ProductMaster,
    quantity: str,
    *,
    unit: str = "dl",
    expires_in: int = 7,
    location: str = "main_fridge",
    status: str = "sealed",
    initial: str | None = None,
    age_minutes: int = 0,
) -> InventoryItem:
    item = InventoryItem(
        id=uuid4(),
        product_master_id=product.id,
        initial_quantity=Decimal(initial or quantity),
        current_quantity=Decimal(quantity),
        unit=unit,
        status=status,
        expiry_date=TODAY + timedelta(days=expires_in),
        location=location,
        created_at=datetime.now(UTC) - timedelta(minutes=age_minutes),
    )
    db.add(item)
    await db.commit()
    return item


async def _fresh(db: AsyncSession, item: InventoryItem) -> InventoryItem:
    found = await db.get(InventoryItem, _id(item), populate_existing=True)
    assert found is not None
    return found


async def _log_rows(db: AsyncSession) -> list[ConsumptionLog]:
    return list((await db.execute(select(ConsumptionLog))).scalars().all())


def _consume(**fields) -> StockConsumeRequest:
    return StockConsumeRequest(**fields)


class TestTheSummary:
    async def test_one_row_per_product_with_totals(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", expires_in=2)
        await _item(db, milk, "10", expires_in=6, location="pantry")

        rows = await stock.stock_summary(db)

        assert len(rows) == 1
        row = rows[0]
        assert row.product_id == _id(milk)
        assert row.product_name == "Milk"
        assert row.category == "dairy"
        assert row.category_icon
        assert (row.unit, row.total, row.item_count) == ("dl", Decimal("15"), 2)
        assert row.earliest_expiry == TODAY + timedelta(days=2)
        assert row.locations == {"main_fridge": Decimal("5"), "pantry": Decimal("10")}
        assert row.expiring is True

    async def test_not_expiring_after_three_days(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", expires_in=4)

        (row,) = await stock.stock_summary(db)

        assert row.expiring is False

    async def test_expired_counts_as_expiring(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", expires_in=-1)

        (row,) = await stock.stock_summary(db)

        assert row.expiring is True

    async def test_gone_items_are_not_stock(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "0", initial="5", status="empty")
        await _item(db, milk, "5", status="discarded")

        assert await stock.stock_summary(db) == []

    async def test_a_second_unit_is_a_second_row(self, db) -> None:
        cheese = await _product(db, "Cheese", unit="g")
        await _item(db, cheese, "400", unit="g")
        await _item(db, cheese, "2", unit="pcs")

        rows = await stock.stock_summary(db)

        assert sorted((r.unit, r.total) for r in rows) == [
            ("g", Decimal("400")),
            ("pcs", Decimal("2")),
        ]

    async def test_sorted_by_earliest_expiry_then_name(self, db) -> None:
        for name, days in (("Yoghurt", 5), ("Butter", 9), ("Cream", 5), ("Apple", 1)):
            await _item(db, await _product(db, name), "1", expires_in=days)

        rows = await stock.stock_summary(db)

        assert [r.product_name for r in rows] == ["Apple", "Cream", "Yoghurt", "Butter"]

    async def test_q_finds_the_canonical_name(self, db) -> None:
        await _item(db, await _product(db, "Oat milk"), "5")
        await _item(db, await _product(db, "Butter"), "5")

        rows = await stock.stock_summary(db, q="MILK")

        assert [r.product_name for r in rows] == ["Oat milk"]

    async def test_q_finds_a_learned_name(self, db) -> None:
        mince = await _product(db, "Ground beef", unit="g", category="meat")
        db.add(
            ProductName(product_master_id=_id(mince), name="jauheliha", source="cook")
        )
        await db.commit()
        await _item(db, mince, "400", unit="g")

        rows = await stock.stock_summary(db, q="jauhe")

        assert [r.product_id for r in rows] == [_id(mince)]

    async def test_q_finds_a_printed_name(self, db) -> None:
        milk = await _product(db, "Milk")
        db.add(
            StoreProductAlias(
                product_master_id=_id(milk),
                store_chain="s-market",
                receipt_name="VALIO KEVYTMAITO 1L",
            )
        )
        await db.commit()
        await _item(db, milk, "10")

        rows = await stock.stock_summary(db, q="kevytmaito")

        assert [r.product_id for r in rows] == [_id(milk)]

    async def test_q_treats_wildcards_literally(self, db) -> None:
        await _item(db, await _product(db, "Milk"), "5")

        assert await stock.stock_summary(db, q="%") == []

    async def test_location_filter_counts_only_that_location(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5")
        await _item(db, milk, "10", location="pantry")

        (row,) = await stock.stock_summary(db, location="pantry")

        assert (row.total, row.item_count) == (Decimal("10"), 1)
        assert row.locations == {"pantry": Decimal("10")}

    async def test_category_and_expiring_days_filters(self, db) -> None:
        await _item(db, await _product(db, "Milk"), "5", expires_in=1)
        await _item(
            db, await _product(db, "Beef", unit="g", category="meat"), "400", unit="g"
        )

        by_category = await stock.stock_summary(db, category="meat")
        soon = await stock.stock_summary(db, expiring_days=2)

        assert [r.product_name for r in by_category] == ["Beef"]
        assert [r.product_name for r in soon] == ["Milk"]


class TestConsumeRequest:
    def test_needs_exactly_one_of_product_and_product_id(self) -> None:
        with pytest.raises(ValidationError):
            _consume(amount=1, unit="dl")
        with pytest.raises(ValidationError):
            _consume(product="milk", product_id=uuid4(), amount=1, unit="dl")

    def test_amount_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _consume(product="milk", amount=0, unit="dl")

    def test_unknown_unit_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _consume(product="milk", amount=1, unit="bucket")


class TestConsumeByName:
    async def test_fifo_across_items(self, db) -> None:
        milk = await _product(db, "Milk")
        later = await _item(db, milk, "10", expires_in=6, age_minutes=10)
        sooner = await _item(db, milk, "5", expires_in=2)

        result = await stock.consume(db, _consume(product="milk", amount=7, unit="dl"))

        assert [c.item_id for c in result.consumed] == [_id(sooner), _id(later)]
        assert [c.amount for c in result.consumed] == [Decimal("5"), Decimal("2")]
        assert [c.remaining for c in result.consumed] == [Decimal("0"), Decimal("8")]
        assert result.consumed[0].status == "empty"
        assert result.consumed[1].status in ("opened", "partial")
        assert (result.remaining_total, result.unit) == (Decimal("8"), "dl")
        assert result.dry_run is False
        assert (await _fresh(db, sooner)).current_quantity == Decimal("0")
        assert (await _fresh(db, later)).current_quantity == Decimal("8")

    async def test_equal_expiry_goes_oldest_first(self, db) -> None:
        milk = await _product(db, "Milk")
        newer = await _item(db, milk, "5")
        older = await _item(db, milk, "5", age_minutes=60)

        result = await stock.consume(db, _consume(product="milk", amount=1, unit="dl"))

        assert [c.item_id for c in result.consumed] == [_id(older)]
        assert (await _fresh(db, newer)).current_quantity == Decimal("5")

    async def test_litres_convert_to_decilitres(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "10")

        result = await stock.consume(
            db, _consume(product="Milk", amount="0.5", unit="l")
        )

        assert result.consumed[0].amount == Decimal("5")
        assert result.requested.amount == Decimal("0.5")
        assert result.requested.unit == "l"
        assert result.remaining_total == Decimal("5")

    async def test_weight_against_a_count_is_invalid(self, db) -> None:
        apples = await _product(db, "Apple", unit="pcs", category="fruits")
        item = await _item(db, apples, "6", unit="pcs")

        with pytest.raises(stock.IncompatibleUnit):
            await stock.consume(db, _consume(product="apple", amount=200, unit="g"))

        assert (await _fresh(db, item)).current_quantity == Decimal("6")
        assert await _log_rows(db) == []

    async def test_short_stock_writes_nothing(self, db) -> None:
        milk = await _product(db, "Milk")
        first = await _item(db, milk, "5", expires_in=1)
        await _item(db, milk, "10", expires_in=3)

        with pytest.raises(stock.InsufficientStock) as raised:
            await stock.consume(db, _consume(product="milk", amount=20, unit="dl"))

        assert (raised.value.available, raised.value.unit) == (Decimal("15"), "dl")
        assert (await _fresh(db, first)).current_quantity == Decimal("5")
        assert await _log_rows(db) == []

    async def test_allow_partial_takes_what_there_is(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5", expires_in=1)
        await _item(db, milk, "10", expires_in=3)

        result = await stock.consume(
            db, _consume(product="milk", amount=20, unit="dl", allow_partial=True)
        )

        assert sum(c.amount for c in result.consumed) == Decimal("15")
        assert all(c.status == "empty" for c in result.consumed)
        assert result.remaining_total == Decimal("0")

    async def test_nothing_in_stock_is_insufficient_even_when_partial(self, db) -> None:
        await _product(db, "Milk")

        with pytest.raises(stock.InsufficientStock) as raised:
            await stock.consume(
                db, _consume(product="milk", amount=1, unit="dl", allow_partial=True)
            )

        assert raised.value.available == Decimal("0")

    async def test_dry_run_writes_nothing(self, db) -> None:
        milk = await _product(db, "Milk")
        sooner = await _item(db, milk, "5", expires_in=2)
        later = await _item(db, milk, "10", expires_in=6)

        result = await stock.consume(
            db, _consume(product="milk", amount=7, unit="dl", dry_run=True)
        )

        assert result.dry_run is True
        assert [c.amount for c in result.consumed] == [Decimal("5"), Decimal("2")]
        assert result.remaining_total == Decimal("8")
        assert (await _fresh(db, sooner)).current_quantity == Decimal("5")
        assert (await _fresh(db, sooner)).status == "sealed"
        assert (await _fresh(db, later)).current_quantity == Decimal("10")
        assert await _log_rows(db) == []

    async def test_one_log_row_per_item_as_a_single_consume_writes_it(self, db) -> None:
        milk = await _product(db, "Milk")
        sooner = await _item(db, milk, "5", expires_in=2)
        later = await _item(db, milk, "10", expires_in=6)

        await stock.consume(db, _consume(product="milk", amount=7, unit="dl"))

        rows = {row.inventory_item_id: row for row in await _log_rows(db)}
        assert set(rows) == {_id(sooner), _id(later)}
        assert rows[_id(sooner)].action == "use_full"
        assert rows[_id(later)].action == "use_partial"
        assert rows[_id(sooner)].quantity_consumed == Decimal("5")
        assert rows[_id(later)].quantity_after == Decimal("8")
        assert rows[_id(sooner)].previous["current_quantity"] == "5.00"
        # Each is its own undo step, as a single-item consume is.
        assert rows[_id(sooner)].batch_id != rows[_id(later)].batch_id

    async def test_location_limits_the_items(self, db) -> None:
        milk = await _product(db, "Milk")
        fridge = await _item(db, milk, "5", expires_in=1)
        pantry = await _item(db, milk, "10", expires_in=5, location="pantry")

        result = await stock.consume(
            db, _consume(product="milk", amount=2, unit="dl", location="pantry")
        )

        assert [c.item_id for c in result.consumed] == [_id(pantry)]
        assert (await _fresh(db, fridge)).current_quantity == Decimal("5")

    async def test_incompatible_items_are_passed_over(self, db) -> None:
        cheese = await _product(db, "Cheese", unit="g")
        await _item(db, cheese, "2", unit="pcs", expires_in=1)
        block = await _item(db, cheese, "400", unit="g", expires_in=5)

        result = await stock.consume(
            db, _consume(product="cheese", amount=100, unit="g")
        )

        assert [c.item_id for c in result.consumed] == [_id(block)]
        assert result.remaining_total == Decimal("300")

    async def test_by_product_id(self, db) -> None:
        milk = await _product(db, "Milk")
        await _item(db, milk, "5")

        result = await stock.consume(
            db, _consume(product_id=_id(milk), amount=1, unit="dl")
        )

        assert (result.product_id, result.product_name) == (_id(milk), "Milk")

    async def test_unknown_product_id_is_not_found(self, db) -> None:
        with pytest.raises(ProductNotFound):
            await stock.consume(db, _consume(product_id=uuid4(), amount=1, unit="dl"))

    async def test_a_learned_name_is_an_exact_hit(self, db) -> None:
        mince = await _product(db, "Ground beef", unit="g", category="meat")
        db.add(
            ProductName(product_master_id=_id(mince), name="jauheliha", source="cook")
        )
        await db.commit()
        await _item(db, mince, "400", unit="g")

        result = await stock.consume(
            db, _consume(product="Jauheliha", amount=100, unit="g")
        )

        assert result.product_id == _id(mince)

    async def test_a_near_miss_is_ambiguous_never_a_guess(self, db) -> None:
        oat = await _product(db, "Oat milk")
        await _item(db, oat, "10")

        with pytest.raises(AmbiguousProduct) as raised:
            await stock.consume(db, _consume(product="milk", amount=1, unit="dl"))

        assert [c.product_id for c in raised.value.candidates] == [_id(oat)]
        candidate = raised.value.candidates[0]
        assert candidate.name == "Oat milk"
        assert 0 < candidate.score <= 1
        assert candidate.source == "canonical"
        assert (await _fresh(db, (await _items_of(db, oat))[0])).current_quantity == 10

    async def test_nothing_like_it_is_not_found(self, db) -> None:
        with pytest.raises(ProductNotFound):
            await stock.consume(db, _consume(product="zyxxy", amount=1, unit="dl"))


async def _items_of(db: AsyncSession, product: ProductMaster) -> list[InventoryItem]:
    return list(
        (
            await db.execute(
                select(InventoryItem).where(
                    InventoryItem.product_master_id == _id(product)
                )
            )
        )
        .scalars()
        .all()
    )
