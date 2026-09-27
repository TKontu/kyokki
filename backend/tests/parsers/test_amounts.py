"""Locale-neutral amounts and line shapes (Q27 verdict #4 and #16)."""

import pytest

from app.parsers.amounts import (
    amount_style,
    detail_count,
    explaining_pair,
    is_detail,
    line_amount,
    strip_amount,
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
            # a unit price is not the line's amount
            "0,523 KG 1,99 €/KG",
            "3 KPL 1,88 €/KPL",
            # codes and numbers without cents on a receipt that prints cents
            "puh. 010 538 7900",
            "Yritys/Ala: 000000000000/5411",
            "**** **** **** 0000 CP",
            "TILAUSNRO: 1089366829",
            "Welcome back",
            # a weight in the middle of a line is not at its end
            "0,913 KG",
        ],
    )
    def test_no_amount(self, line):
        assert line_amount(line) is None


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
        assert amount_style(["MAITO 1,29", "puh. 010 538 7900"]) == "cents"

    @pytest.mark.parametrize(
        ("line", "amount"),
        [
            ("MILK 198", 198),
            ("BREAD 1,280", 1280),
            ("CHEESE 1.299", 1299),
            ("TOTAL 2,777", 2777),
            ("ÖSSZESEN 12990 Ft", 12990),
            ("Mjölk 1 L 15,90 kr", 15.9),
            ("No. 0042", None),
            ("Tel 03-1234-5678", None),
        ],
    )
    def test_whole_amounts(self, line, amount):
        assert line_amount(line, "whole") == amount

    def test_whole_numbers_do_not_count_on_a_receipt_with_cents(self):
        assert line_amount("MILK 198", "cents") is None


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
            ("3 kom x 1,29", True),
            ("7UP 1,5L 2,49", True),  # by shape; only its arithmetic can attach it
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
            # a missed product is not the detail line of the one above it
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
