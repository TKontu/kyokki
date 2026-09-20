"""One set of status rules for consuming and correcting quantities (MVP-C2, MVP-S4, H23).

The table itself is `contracts/status-transitions.json`, read by this file and by
`frontend/lib/__tests__/consumption.test.ts`. The rule is written twice - once on the server,
once in the iPad's optimistic update - and the shared file is what stops the two drifting.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.crud.inventory_item import _start_opened_clock
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.item_status import (
    PARTIAL_THRESHOLD,
    ItemEvent,
    ItemFrozen,
    is_frozen,
    next_status,
    opens_the_pack,
)

CONTRACT = json.loads(
    (
        Path(__file__).resolve().parents[3] / "contracts" / "status-transitions.json"
    ).read_text(encoding="utf-8")
)


def _item(status: str = "sealed", initial: int = 10, opened: date | None = None):
    return InventoryItem(
        initial_quantity=Decimal(initial),
        current_quantity=Decimal(initial),
        status=status,
        opened_date=opened,
    )


class TestTheSharedTable:
    """Every case in `contracts/status-transitions.json`, server side."""

    @pytest.mark.parametrize(
        "case", CONTRACT["cases"], ids=[c["name"] for c in CONTRACT["cases"]]
    )
    def test_case(self, case) -> None:
        assert (
            next_status(
                current=case["from"],
                event=ItemEvent(case["event"]),
                initial=Decimal(str(case["initial"])),
                remaining=Decimal(str(case["remaining"])),
                opened=case["opened"],
            )
            == case["to"]
        )

    @pytest.mark.parametrize(
        "case", CONTRACT["refused"], ids=[c["name"] for c in CONTRACT["refused"]]
    )
    def test_refused(self, case) -> None:
        with pytest.raises(ItemFrozen):
            next_status(
                current=case["from"],
                event=ItemEvent(case["event"]),
                initial=Decimal(10),
                remaining=Decimal(4),
                opened=True,
            )

    def test_the_threshold_is_the_one_both_sides_use(self) -> None:
        assert Decimal(str(CONTRACT["partialThreshold"])) == PARTIAL_THRESHOLD


class TestFrozen:
    """Q12 gave the freezer its own expiry source; H23 gives the bin its own rule."""

    def test_only_discarded_refuses_writes(self) -> None:
        assert is_frozen("discarded")
        for live in ("sealed", "opened", "partial", "empty"):
            assert not is_frozen(live)

    def test_the_refusal_names_the_event(self) -> None:
        with pytest.raises(ItemFrozen) as caught:
            next_status(
                current="discarded",
                event=ItemEvent.CONSUME,
                initial=Decimal(10),
                remaining=Decimal(9),
                opened=True,
            )

        assert caught.value.status == "discarded"
        assert caught.value.event is ItemEvent.CONSUME
        assert "Restore it first" in str(caught.value)


class TestOpensThePack:
    """The edge Q5's opened clock hangs on, named instead of re-derived."""

    @pytest.mark.parametrize("to", ["opened", "partial", "empty"])
    def test_a_sealed_pack_going_anywhere_else_opens_it(self, to) -> None:
        assert opens_the_pack("sealed", to)

    def test_a_sealed_pack_staying_sealed_does_not(self) -> None:
        assert not opens_the_pack("sealed", "sealed")

    @pytest.mark.parametrize("current", ["opened", "partial", "empty"])
    def test_an_already_open_pack_is_not_opened_again(self, current) -> None:
        assert not opens_the_pack(current, "partial")


SEALED_EXPIRY = date(2026, 12, 1)


class TestOpenedClock:
    """Q5: an opened pack stops claiming the shelf life it had sealed.

    Unchanged by H23 - the clock moved call site, not behaviour - and these are the six
    invariants that say so.
    """

    def _item(self, *, opened_days: int | None, piece_grams: Decimal | None = None):
        product = ProductMaster(
            canonical_name="Sour cream",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=30,
            opened_shelf_life_days=opened_days,
            avg_piece_grams=piece_grams,
            unit_type="volume",
            default_unit="dl",
        )
        item = InventoryItem(
            initial_quantity=Decimal(10),
            current_quantity=Decimal(10),
            status="sealed",
            expiry_date=SEALED_EXPIRY,
            opened_date=date.today(),
        )
        item.product_master = product
        return item

    def test_opening_brings_the_expiry_forward(self) -> None:
        item = self._item(opened_days=5)

        _start_opened_clock(item)

        assert item.expiry_date == date.today() + timedelta(days=5)

    def test_opening_never_pushes_the_expiry_out(self) -> None:
        """A jar opened the day before its printed date does not gain a fortnight."""
        item = self._item(opened_days=5)
        item.expiry_date = date.today() + timedelta(days=1)

        _start_opened_clock(item)

        assert item.expiry_date == date.today() + timedelta(days=1)

    def test_loose_produce_is_not_a_pack(self) -> None:
        """Taking one apple out of a bowl of thirteen does not open anything."""
        item = self._item(opened_days=2, piece_grams=Decimal("125"))

        _start_opened_clock(item)

        assert item.expiry_date == SEALED_EXPIRY

    def test_without_an_opened_shelf_life_nothing_happens(self) -> None:
        item = self._item(opened_days=None)

        _start_opened_clock(item)

        assert item.expiry_date == SEALED_EXPIRY

    def test_without_a_product_nothing_happens(self) -> None:
        item = self._item(opened_days=5)
        item.product_master = None

        _start_opened_clock(item)

        assert item.expiry_date == SEALED_EXPIRY
