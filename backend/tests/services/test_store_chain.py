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
