"""Optional receipt profiles: extra evidence for a known country or language (Q27)."""

from pathlib import Path

import pytest

from app.parsers.profiles import FinnishProfile, ProfileLine, profile_for
from app.services.llm_extractor import number_receipt_lines

FIXTURES = Path(__file__).parent.parent / "fixtures" / "receipts"


class TestRegistry:
    @pytest.mark.parametrize(
        ("country", "language"),
        [("FI", None), ("fi", None), (None, "fi"), ("FI", "sv"), (None, "FI")],
    )
    def test_finland_or_finnish_selects_the_finnish_profile(self, country, language):
        assert isinstance(profile_for(country, language), FinnishProfile)

    @pytest.mark.parametrize(
        ("country", "language"),
        [("HR", "hr"), ("DE", "de"), ("GB", "en"), (None, None), ("", "")],
    )
    def test_no_profile_for_other_receipts(self, country, language):
        assert profile_for(country, language) is None


class TestFinnishProfile:
    def test_reads_the_k_receipt_with_the_prompts_line_numbers(self):
        text = (FIXTURES / "k_citymarket_sello.txt").read_text(encoding="utf-8")
        numbered = number_receipt_lines(text)
        prompt_lines = {n: line for n, line in numbered if n is not None}

        lines = FinnishProfile().product_lines(numbered)

        assert len(lines) == 15
        entrecote = lines[3]
        assert entrecote.name == "Naudan Entrecote Palana"
        assert entrecote.weight_kg == 0.913
        # the name line and its weight line, as the model sees them
        assert [prompt_lines[n] for n in entrecote.line_numbers] == [
            "Naudan Entrecote Palana 22,83",
            "0,913 KG 25,00 €/KG",
        ]
        soap = lines[9]
        assert (soap.name, soap.quantity) == ("Palmolive Vaahtosaippua 250ml", 2)
        assert len(soap.line_numbers) == 2

    def test_cites_only_numbered_lines(self):
        numbered = [(None, "MAITO 1,20"), (1, "LEIPÄ 2,10")]
        assert FinnishProfile().product_lines(numbered) == [
            ProfileLine(line_numbers=(1,), name="LEIPÄ")
        ]
