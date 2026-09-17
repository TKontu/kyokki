"""One set of status rules for consuming and correcting quantities (MVP-C2, MVP-S4)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.crud.inventory_item import apply_quantity_status
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster


def _item(status: str = "sealed", initial: int = 10, opened: date | None = None):
    return InventoryItem(
        initial_quantity=Decimal(initial),
        current_quantity=Decimal(initial),
        status=status,
        opened_date=opened,
    )


@pytest.mark.parametrize(
    ("start", "quantity", "status", "opened"),
    [
        ("sealed", 10, "sealed", False),
        ("sealed", 9, "opened", True),
        ("sealed", 7.5, "opened", True),
        ("sealed", 7, "partial", True),
        ("sealed", 0, "empty", False),
        ("opened", 3, "partial", False),
        ("empty", 3, "partial", False),
        ("empty", 10, "opened", False),
        ("partial", 10, "partial", False),
    ],
)
def test_status_follows_the_remaining_share(start, quantity, status, opened):
    item = _item(start)

    apply_quantity_status(item, Decimal(str(quantity)))

    assert item.status == status
    assert (item.opened_date == date.today()) is opened


def test_first_drop_keeps_an_existing_opened_date():
    item = _item("opened", opened=date(2026, 1, 1))

    apply_quantity_status(item, Decimal(5))

    assert item.opened_date == date(2026, 1, 1)


SEALED_EXPIRY = date(2026, 12, 1)


def _pack(
    unit: str = "dl",
    opened_days: int | None = 5,
    expiry: date = SEALED_EXPIRY,
    piece_grams: Decimal | None = None,
):
    """An unopened item whose product may or may not know its opened shelf life."""
    product = ProductMaster(
        canonical_name="Cream",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=14,
        opened_shelf_life_days=opened_days,
        avg_piece_grams=piece_grams,
        unit_type="volume",
        default_unit=unit,
    )
    item = InventoryItem(
        initial_quantity=Decimal(10),
        current_quantity=Decimal(10),
        unit=unit,
        status="sealed",
        expiry_date=expiry,
        expiry_source="calculated",
    )
    item.product_master = product
    return item


class TestOpenedClock:
    """Q5: opening a pack starts a shorter clock."""

    def test_opening_a_pack_brings_the_expiry_forward(self):
        item = _pack()

        apply_quantity_status(item, Decimal(9))

        assert item.opened_date == date.today()
        assert item.expiry_date == date.today() + timedelta(days=5)

    def test_opening_never_pushes_the_expiry_out(self):
        """A jar opened the day before its printed date does not gain five days."""
        tomorrow = date.today() + timedelta(days=1)
        item = _pack(expiry=tomorrow)

        apply_quantity_status(item, Decimal(9))

        assert item.expiry_date == tomorrow

    def test_taking_one_apple_does_not_shorten_the_other_twelve(self):
        """Loose produce is not a pack: a fruit bowl is not opened by eating from it."""
        item = _pack(unit="pcs", piece_grams=Decimal("125"))
        item.initial_quantity = Decimal(13)
        item.current_quantity = Decimal(13)

        apply_quantity_status(item, Decimal(12))

        assert item.expiry_date == SEALED_EXPIRY

    def test_a_carton_counted_as_one_piece_still_gets_the_clock(self):
        """A litre of milk is stored as 1 pcs; counting in pieces cannot be the test."""
        item = _pack(unit="pcs")
        item.initial_quantity = Decimal(1)
        item.current_quantity = Decimal(1)

        apply_quantity_status(item, Decimal("0.5"))

        assert item.expiry_date == date.today() + timedelta(days=5)

    def test_a_product_with_no_opened_shelf_life_is_left_alone(self):
        item = _pack(opened_days=None)

        apply_quantity_status(item, Decimal(9))

        assert item.expiry_date == SEALED_EXPIRY

    def test_consuming_again_does_not_restart_the_clock(self):
        item = _pack()
        apply_quantity_status(item, Decimal(9))
        shortened = item.expiry_date

        apply_quantity_status(item, Decimal(4))

        assert item.expiry_date == shortened
