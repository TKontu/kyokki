"""One set of status rules for consuming and correcting quantities (MVP-C2, MVP-S4)."""

from datetime import date
from decimal import Decimal

import pytest

from app.crud.inventory_item import apply_quantity_status
from app.models.inventory_item import InventoryItem


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
