"""Store header text → stable chain key used to scope aliases."""

import pytest

from app.parsers.heuristic import parse_receipt_text
from app.services.store_chain import _CHAINS, normalize_store_chain


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
        # F1: a plain (non-confusion) substitution must never count, regardless of length
        "PRIIMA PERUNA 2KG 1,99",  # the F1 repro - a product line, not a Prisma receipt
        "PRIIMA",  # I/S at that position is not a confusion pair
        "ALEPPO",  # a real place name, more than one edit from ALEPA
        # F5: two confusion-type edits at once must not collapse to "one edit"
        "IIDI",  # LIDL with *both* Ls misread as I - two edits, not one
    ],
)
def test_ocr_misread_tolerance_has_no_false_positives(raw):
    result = normalize_store_chain(raw)
    assert result not in ("s-group", "k-group", "lidl", "tokmanni")


def _one_non_confusion_edit_away(pattern: str) -> str:
    """`pattern` with its last character swapped for one that is not its OCR confusion.

    Mutating a real pattern (rather than picking arbitrary words) is what keeps this
    general: it stays a meaningful negative case however `_CHAINS` or the confusion table
    change, instead of a fixed list going stale.
    """
    replacement = "Q" if pattern[-1] != "Q" else "Z"
    return pattern[:-1] + replacement


@pytest.mark.parametrize(
    "pattern",
    [pattern for _, patterns in _CHAINS for pattern in patterns if len(pattern) >= 5],
)
def test_one_non_confusion_edit_from_a_long_pattern_does_not_match(pattern):
    """An ordinary-looking word one (non-confusion) substitution from a ≥5-char pattern.

    Generated from `_CHAINS` itself (F1): whatever patterns the table holds, a word that
    differs from one of them only by an edit that is not a known OCR confusion must stay
    unmatched, however long the pattern is.
    """
    mutated = _one_non_confusion_edit_away(pattern)

    result = normalize_store_chain(mutated)

    assert result not in ("s-group", "k-group", "lidl", "tokmanni")


def test_a_store_genuinely_not_in_the_table_stays_a_slug():
    assert normalize_store_chain("Ruohonjuuri Osuuskunta") == "ruohonjuuri-osuuskunta"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # F3: OCR reading a chain's hyphen as a plain space
        ("K Citymarket Ruoholahti", "k-group"),
        ("S market", "s-group"),
    ],
)
def test_a_hyphen_read_as_a_space_still_finds_the_chain(raw, expected):
    assert normalize_store_chain(raw) == expected


def test_heuristic_header_detection_assigns_no_chain_to_product_lines():
    """`parsers/heuristic.py` (read-only here) must not see a chain in ordinary products.

    The header-detection fuzzy pass runs on every one of the first few lines the heuristic
    parser considers (`_HEADER_LINES` in `heuristic.py`), so a receipt whose own first lines
    are product lines - no store header at all - must still come back with no chain, even
    with a line that resembles the F1 false positive among them.
    """
    text = "\n".join(
        [
            "PRIIMA PERUNA 2KG 1,99",
            "VALIO MAITO 1L 1,49",
            "RUISLEIPA 500G 2,29",
            "YHTEENSÄ 5,77",
        ]
    )

    result = parse_receipt_text(text)

    assert result.store_chain is None
