"""Canonical unit conversion (operator ruling: dl | tsp | tbsp | g | pcs)."""

import pytest

from app.services.units import receipt_line_quantity, to_canonical


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
        ],
    )
    def test_converts_to_canonical_units(self, value, unit, expected):
        assert to_canonical(value, unit) == expected

    def test_rounds_to_two_decimals(self):
        assert to_canonical(0.12345, "kg") == (123.45, "g")
        assert to_canonical(1, "ml") == (0.01, "dl")

    def test_accepts_whitespace_and_case(self):
        assert to_canonical(1, " L ") == (10.0, "dl")

    @pytest.mark.parametrize("unit", ["oz", "", "tsp", "bag"])
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
