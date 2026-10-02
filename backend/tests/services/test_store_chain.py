"""Store header text → stable chain key used to scope aliases."""

import pytest

from app.services.store_chain import normalize_store_chain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("S-KAUPAT", "s-group"),
        ("Prisma", "s-group"),
        ("Prisma ruoan verkkokauppa", "s-group"),
        ("S-Market Kamppi", "s-group"),
        ("Alepa", "s-group"),
        ("HOK-ELANTO LIIKETOIMINTA OY", "s-group"),
        ("K-Citymarket Ruoholahti", "k-group"),
        ("K-MARKET", "k-group"),
        ("K-Ruoka", "k-group"),
        ("Kesko", "k-group"),
        ("LIDL", "lidl"),
        ("Tokmanni Oy", "tokmanni"),
    ],
)
def test_known_chains(raw, expected):
    assert normalize_store_chain(raw) == expected


def test_unknown_store_becomes_a_slug():
    assert normalize_store_chain("  Ruohonjuuri Kamppi ") == "ruohonjuuri-kamppi"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_is_none(raw):
    assert normalize_store_chain(raw) is None


def test_already_normalised_key_is_stable():
    assert normalize_store_chain("s-group") == "s-group"
    assert normalize_store_chain("k-group") == "k-group"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # OCR misreads of the chain word itself (Q37 follow-up)
        ("Lidi Suomi Ky Espoo-Karakall1o", "lidl"),
        ("LIDI", "lidl"),
        ("K-CITYMARKT Ruoholahti", "k-group"),
        ("PRISNA ruoan verkkokauppa", "s-group"),
    ],
)
def test_ocr_misread_still_finds_the_chain(raw, expected):
    assert normalize_store_chain(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "SALT",  # distance 1 from SALE, but T/E is not an OCR confusion pair
        "SOKERI",  # distance >1 from every known pattern
        "LIDO",  # distance 1 from LIDL, but O/L is not an OCR confusion pair
        "MAITO",  # an ordinary Finnish word (milk), not close to any chain pattern
        "KAHVI",  # an ordinary Finnish word (coffee), not close to any chain pattern
    ],
)
def test_ocr_misread_tolerance_has_no_false_positives(raw):
    result = normalize_store_chain(raw)
    assert result not in ("s-group", "k-group", "lidl", "tokmanni")


def test_a_store_genuinely_not_in_the_table_stays_a_slug():
    assert normalize_store_chain("Ruohonjuuri Osuuskunta") == "ruohonjuuri-osuuskunta"
