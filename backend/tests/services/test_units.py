"""Canonical unit conversion (operator ruling: dl | tsp | tbsp | g | pcs)."""

from decimal import Decimal

import pytest

from app.services.units import (
    canonical_factor,
    receipt_line_quantity,
    to_canonical,
    to_canonical_decimal,
    unit_type_for,
)


class TestToCanonical:
    @pytest.mark.parametrize(
        ("value", "unit", "expected"),
        [
            (0.386, "kg", (386.0, "g")),
            (150, "g", (150.0, "g")),
            (1.5, "l", (15.0, "dl")),
            (2, "dl", (2.0, "dl")),
            (33, "cl", (3.3, "dl")),
            (330, "ml", (3.3, "dl")),
            (3, "pcs", (3.0, "pcs")),
            (3, "KPL", (3.0, "pcs")),
            (1, "unit", (1.0, "pcs")),
            (2, "st", (2.0, "pcs")),
            (1, "tsp", (1.0, "tsp")),
            (2, "TBSP", (2.0, "tbsp")),
        ],
    )
    def test_converts_to_canonical_units(self, value, unit, expected):
        assert to_canonical(value, unit) == expected

    def test_rounds_to_two_decimals(self):
        assert to_canonical(0.12345, "kg") == (123.45, "g")
        assert to_canonical(1, "ml") == (0.01, "dl")

    def test_accepts_whitespace_and_case(self):
        assert to_canonical(1, " L ") == (10.0, "dl")

    @pytest.mark.parametrize("unit", ["oz", "", "cup", "bag"])
    def test_unknown_units_raise(self, unit):
        with pytest.raises(ValueError):
            to_canonical(1, unit)


class TestReceiptLineQuantity:
    def test_weight_line_becomes_grams(self):
        assert receipt_line_quantity(1, 0.386) == (386.0, "g")

    def test_count_line_becomes_pieces(self):
        assert receipt_line_quantity(3, None) == (3.0, "pcs")

    def test_missing_or_zero_quantity_defaults_to_one_piece(self):
        assert receipt_line_quantity(None, None) == (1.0, "pcs")
        assert receipt_line_quantity(0, None) == (1.0, "pcs")


class TestDecimalConversion:
    def test_canonical_factor(self):
        assert canonical_factor(" ML ") == (Decimal("0.01"), "dl")
        assert canonical_factor("tsp") == (Decimal("1"), "tsp")

    def test_quantizes_to_cents(self):
        assert to_canonical_decimal(Decimal("330"), "ml") == Decimal("3.30")
        assert to_canonical_decimal(Decimal("0.4"), "kg") == Decimal("400.00")
        assert to_canonical_decimal(Decimal("1"), "ml") == Decimal("0.01")

    def test_none_stays_none(self):
        assert to_canonical_decimal(None, "l") is None

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError):
            to_canonical_decimal(Decimal("1"), "oz")


class TestUnitType:
    @pytest.mark.parametrize(
        ("unit", "kind"),
        [
            ("dl", "volume"),
            ("tsp", "volume"),
            ("tbsp", "volume"),
            ("g", "weight"),
            ("pcs", "count"),
            ("ml", "volume"),
            ("kg", "weight"),
        ],
    )
    def test_unit_type(self, unit, kind):
        assert unit_type_for(unit) == kind
