"""Store-agnostic receipt line parser used when LLM extraction fails (MVP-R3b)."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.parsers.heuristic import parse_receipt_text

FIXTURES = Path(__file__).parent.parent / "fixtures" / "receipts"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestSKaupatOrder:
    """The 60-line S-kaupat order from docs/vLLM_MANUAL_TEST.md (Test 2)."""

    @pytest.fixture
    def expected(self) -> dict:
        return json.loads(_read("expected_s_kaupat.json"))

    @pytest.fixture
    def result(self):
        return parse_receipt_text(_read("s_kaupat_order.txt"))

    def test_reads_at_least_80_percent_of_product_lines(self, result, expected):
        names = [line.name for line in result.lines]
        wanted = [line["name"] for line in expected["lines"]]
        found = sum(1 for name in wanted if name in names)

        assert found / len(wanted) >= 0.8
        # The grammar is aimed at exact results on this receipt
        assert names == wanted

    def test_quantities_and_weights_land_on_their_products(self, result, expected):
        got = {line.name: (line.quantity, line.weight_kg) for line in result.lines}
        for line in expected["lines"]:
            assert got[line["name"]] == (line["quantity"], line["weight_kg"]), line[
                "name"
            ]

    def test_fees_discounts_totals_and_payment_are_not_products(self, result):
        joined = " ".join(line.name for line in result.lines)
        for word in (
            "TOIMITUSMAKSU",
            "VERKKOK",
            "NORM.",
            "ALENNUS",
            "VÄLISUMMA",
            "YHTEENSÄ",
            "BONUSTA",
            "Veloitus",
            "YHT.",
        ):
            assert word not in joined

    def test_store_and_date(self, result, expected):
        assert result.method == "heuristic"
        assert result.store_chain == "S-KAUPAT"
        assert result.purchase_date == date(2026, 1, 2)

    def test_no_generic_names_or_categories(self, result):
        assert all(
            line.generic_name is None and line.category is None for line in result.lines
        )


class TestKGroupPhoto:
    @pytest.fixture
    def result(self):
        return parse_receipt_text(_read("k_group.txt"))

    def test_products_quantities_and_weights(self, result):
        assert [
            (line.name, line.quantity, line.weight_kg) for line in result.lines
        ] == [
            ("Pilsner Urquell 4,4% 0,5l tlk", 1, None),
            ("Mutti kuoritut tomaatit 400g", 2, None),
            ("Pirkka juustor 150g emment-moz", 2, None),
            ("Banaani", 1, 0.412),
        ]

    def test_store_and_date(self, result):
        assert result.store_chain == "K-Citymarket Ruoholahti"
        assert result.purchase_date == date(2026, 3, 5)


class TestLidlEReceipt:
    @pytest.fixture
    def result(self):
        return parse_receipt_text(_read("lidl.txt"))

    def test_products_without_vat_codes_or_savings(self, result):
        assert [
            (line.name, line.quantity, line.weight_kg) for line in result.lines
        ] == [
            ("Grillimaisteri bratwurst", 1, None),
            ("Tosco.Bonus.ital.makk.c", 1, None),
            ("Sandels 4,7% 24-pack", 1, None),
            ("Päärynä", 1, 0.436),
            ("Eridanous halloumi", 2, None),
            ("Baresa vihr.täyt.oliiv.p", 2, None),
        ]

    def test_store_and_date(self, result):
        assert result.store_chain == "Lidl"
        assert result.purchase_date == date(2026, 4, 12)


class TestEdgeCases:
    def test_empty_text(self):
        result = parse_receipt_text("")
        assert result.lines == []
        assert (result.store_chain, result.purchase_date) == (None, None)

    def test_detail_line_before_any_product_is_ignored(self):
        result = parse_receipt_text("3 KPL 1,88 €/KPL\n0,330 KG 1,59 €/KG\nMAITO 1,20")
        assert [
            (line.name, line.quantity, line.weight_kg) for line in result.lines
        ] == [("MAITO", 1, None)]

    def test_price_lines_without_words_are_ignored(self):
        text = "25,5% 31,13 7,93 39,06\nA 25,5 22,57 5,75 28,32\n123 4,50\nLEIPÄ 2,10"
        assert [line.name for line in parse_receipt_text(text).lines] == ["LEIPÄ"]

    def test_invalid_dates_are_skipped(self):
        result = parse_receipt_text("31.02.2026\n01.03.2026 12:00\nMAITO 1,20")
        assert result.purchase_date == date(2026, 3, 1)

    def test_names_keep_percent_signs_and_sizes(self):
        result = parse_receipt_text(
            "RANSKANKERMA 18% VÄHÄLAKT 0,75\nPORKKANA 1KG 5,45\n5 KPL 1,09 €/KPL"
        )
        assert [(line.name, line.quantity) for line in result.lines] == [
            ("RANSKANKERMA 18% VÄHÄLAKT", 1),
            ("PORKKANA 1KG", 5),
        ]

    def test_unicode_minus_discounts_are_skipped(self):
        text = "JUUSTO 4,30\nETU −0,50\nKAMPANJA 0,30–\nLEIPÄ 2,10"
        assert [line.name for line in parse_receipt_text(text).lines] == [
            "JUUSTO",
            "LEIPÄ",
        ]
