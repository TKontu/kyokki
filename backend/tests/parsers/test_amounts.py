"""Locale-neutral amounts and line shapes (Q27 verdict #4 and #16; PR #131 F3-F10).

Card and phone strings here are obviously fake (zeros only).
"""

import pytest

from app.parsers.amounts import (
    amount_style,
    clock_time,
    detail_count,
    explaining_pair,
    is_detail,
    line_amount,
    receipt_units,
    strip_amount,
    wraps_onto,
)


class TestLineAmount:
    @pytest.mark.parametrize(
        ("line", "amount"),
        [
            ("Bakerika suol suklaahipkeksita 4,27", 4.27),
            ("WHOLE MILK 1 GAL 3.49", 3.49),
            ("Credit/Veloitus 73,07 EUR", 73.07),
            ("Joghurt Natur 150g           2,67 B", 2.67),
            ("TOTAL $7.00", 7.0),
            ("ALENNUS -1,14", -1.14),
            ("RABATT 1,14-", -1.14),
            ("TV 1.299,00", 1299.0),
            ("TV 1,299.00", 1299.0),
            ("TV 1'299.00", 1299.0),
            ("  2 kom x 1,29                  2,58", 2.58),
            ("2 x 1,49", 1.49),
            # PR #131 F5: any short trailing marker, any currency symbol or code
            ("MILK 3.49 FS", 3.49),
            ("PAIN 0,95 1", 0.95),
            ("ARROZ R$ 12,90", 12.9),
            ("ARROZ 12,90 R$", 12.9),
            ("ХЛІБ 25,50 ₴", 25.5),
            ("KAFFE 45,90 NOK", 45.9),
            ("MLÉKO 24,90 Kč", 24.9),
            ("SÖR 12,90 Ft", 12.9),
            ("BREAD 1,99*", 1.99),
            # PR #131 F10: space-grouped thousands
            ("PAN 1 234,56", 1234.56),
            ("PAN 1 234,56", 1234.56),
        ],
    )
    def test_an_amount_at_the_end_of_the_line(self, line, amount):
        assert line_amount(line) == amount

    @pytest.mark.parametrize(
        "line",
        [
            # a clock time, a date and a cashier code (the K receipt's line 6)
            "K004 M000000/0000 11.49 26.9.2026",
            "26.9.2026 11.49",
            "Kello 11:49",
            "Datum: 27.09.2026   Uhrzeit: 18:05",
            "09/27/2026 10:15 AM",
            # PR #131 F3: a time after a date on the same line, whatever word is between
            "Kuitti 27.9.2026 klo 18.05",
            "27.09.2026 Time 12.30",
            # a unit price is not the line's amount
            "0,523 KG 1,99 €/KG",
            "3 KPL 1,88 €/KPL",
            # codes and numbers without cents on a receipt that prints cents
            "puh. 000 000 0000",
            "Yritys/Ala: 000000000000/0000",
            "**** **** **** 0000 CP",
            "TILAUSNRO: 0000000000",
            "Welcome back",
            # a weight in the middle of a line is not at its end
            "0,913 KG",
            # PR #131 F4: a masked card number
            "CARD ****0000",
            "VISA **** 0000",
        ],
    )
    def test_no_amount(self, line):
        assert line_amount(line) is None

    def test_the_name_keeps_nothing_of_a_space_grouped_amount(self):
        assert strip_amount("PAN 1 234,56") == "PAN"


class TestWholeCurrencyReceipts:
    """JPY or HUF: amounts without cents count only on a receipt that prints no cents."""

    LINES = [
        "SHOP",
        "MILK 198",
        "BREAD 1,280",
        "CHEESE 1.299",
        "No. 0042",
        "TOTAL 2,777",
    ]

    def test_the_style_is_read_off_the_receipt(self):
        assert amount_style(self.LINES) == "whole"
        assert amount_style(["MAITO 1,29", "puh. 000 000 0000"]) == "cents"

    @pytest.mark.parametrize(
        ("line", "amount"),
        [
            ("MILK 198", 198),
            ("BREAD 1,280", 1280),
            ("CHEESE 1.299", 1299),
            ("TOTAL 2,777", 2777),
            ("ÖSSZESEN 12990 Ft", 12990),
            ("ÖSSZESEN 12 990 Ft", 12990),
            ("Mjölk 1 L 15,90 kr", 15.9),
            ("No. 0042", None),
            ("Tel 00-0000-0000", None),
            # PR #131 F5: a Japanese marker after the amount
            ("¥1,280※", 1280),
            ("RICE 1,280 軽", 1280),
            # PR #131 F4: phone and card fragments are not prices
            ("TEL 000 0000", None),
            ("TEL 00 0000 0000", None),
            ("VISA **** 0000", None),
            ("CARD ****0000", None),
        ],
    )
    def test_whole_amounts(self, line, amount):
        assert line_amount(line, "whole") == amount

    def test_whole_numbers_do_not_count_on_a_receipt_with_cents(self):
        assert line_amount("MILK 198", "cents") is None


class TestThreeDecimalCurrencies:
    """PR #131 F7: `1.250` KWD read as 1250. The model's total gives the precision."""

    LINES = ["SHOP", "MILK 1.250", "BREAD 0.800", "CHEESE 1.100", "TOTAL 3.150"]

    def test_a_three_decimal_total_makes_three_decimal_amounts(self):
        assert amount_style(self.LINES, total=3.15) == "mills"
        assert line_amount("MILK 1.250", "mills") == 1.25
        assert line_amount("TOTAL 3.150", "mills") == 3.15

    def test_without_that_total_they_read_as_thousands(self):
        assert amount_style(self.LINES) == "whole"
        assert amount_style(self.LINES, total=3150) == "whole"
        assert line_amount("MILK 1.250", "whole") == 1250


class TestUnitsAreNotCurrencies:
    """PR #131 F4: `2,49 KPL` is a count unit, not a currency code."""

    LINES = ["SHOP", "3 KPL 1,88 €/KPL", "0,736 kg x 2,49 EUR/kg", "Tuote 2,49 KPL"]

    def test_the_receipt_names_its_units(self):
        assert {"kpl", "kg"} <= receipt_units(self.LINES)

    def test_a_trailing_unit_of_this_receipt_is_no_amount(self):
        units = receipt_units(self.LINES)
        assert line_amount("Tuote 2,49 KPL", "cents", units) is None
        assert line_amount("Tuote 2,49 EUR", "cents", units) == 2.49
        assert line_amount("Tuote 2,49 B", "cents", units) == 2.49


class TestClockTimes:
    """PR #131 F3: a clock time after a short word is a weak amount (see
    `receipt_processing`): it counts only when the sums miss a listed total."""

    @pytest.mark.parametrize(
        ("line", "time"),
        [
            ("KLO 11.49", True),
            ("Time 12.30", True),
            ("klo 18.05", True),
            ("at 9.15", True),
            ("KLO 25.49", False),  # no such hour
            ("KLO 11.75", False),  # no such minute
            ("MAITO 1.29", False),  # a word of five letters is a name
            ("PEAR BIO 1.29", False),  # two words are a name
        ],
    )
    def test_clock_time_shape(self, line, time):
        assert clock_time(line) is time


class TestNamesAndDetailLines:
    def test_a_name_is_the_line_without_its_amount(self):
        assert (
            strip_amount("Joghurt Natur 150g           2,67 B") == "Joghurt Natur 150g"
        )
        assert strip_amount("Vollmilch 3,5% 1L 2,98") == "Vollmilch 3,5% 1L"
        assert strip_amount("JUUSTO GOUDA") == "JUUSTO GOUDA"

    @pytest.mark.parametrize(
        ("line", "detail"),
        [
            ("0,913 KG 25,00 €/KG", True),
            ("2 x 1,49", True),
            ("2x1,49", True),
            ("3 kom x 1,29", True),
            # PR #131 F2/F15: a name that starts with digits is a name
            ("7UP 1,5L 2,49", False),
            ("1,5L COLA 2,49", False),
            ("Vollmilch 3,5% 1L 2,98", False),
        ],
    )
    def test_detail_shape(self, line, detail):
        assert is_detail(line) is detail

    @pytest.mark.parametrize(
        ("line", "total", "explains"),
        [
            ("2 x 1,49", 2.98, True),
            ("0,913 KG 25,00 €/KG", 22.83, True),
            ("0,523 KG 1,99 €/KG", 1.04, True),
            ("0,845 kg x 1,99               1,68", 1.68, True),
            ("2 KPL 2,49 €/KPL", 4.98, True),
            ("7UP 1,5L 2,49", 1.99, False),
            ("3 x 0,89", 2.29, False),
            ("2 x 1,49", None, False),
        ],
    )
    def test_the_arithmetic_proves_a_detail_line(self, line, total, explains):
        assert (explaining_pair(line, total) is not None) is explains

    def test_a_count_line_gives_the_count(self):
        assert detail_count("2 x 1,49", 2.98) == 2
        assert detail_count("3 kom x 1,29", 3.87) == 3
        assert detail_count("0,913 KG 25,00 €/KG", 22.83) is None

    @pytest.mark.parametrize(
        ("first", "second", "wraps"),
        [
            ("Čokolada mliječna s lješnjacima", "i grožđicama 100g 2,19", True),
            # PR #131 F9: an all-caps till wraps in capitals
            ("VALIO LUOMU LAKTOOSITON", "KEVYTMAITOJUOMA 1L 1,29", True),
            ("KORTTI: 0000", "LEIPÄ 2,10", False),
            ("K004 M000000/0000", "BAKERIKA 4,27", False),
            ("Welcome", "MAITO 1,20", False),
        ],
    )
    def test_a_wrapped_first_half(self, first, second, wraps):
        assert wraps_onto(first, second) is wraps
