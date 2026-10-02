"""Normalise store header text to a stable chain key.

The extraction model reads whatever the header says (``S-KAUPAT``, ``Prisma ruoan
verkkokauppa``, ``K-Citymarket Ruoholahti``). Store aliases are scoped by chain, so every
variant of the same chain must map to one key.

OCR sometimes misreads the chain word itself (``Lidi Suomi Ky`` for a Lidl receipt). After the
exact pass fails, a fuzzy pass tolerates a single edit between a header word and a known
pattern, so the receipt still lands on the real chain instead of inventing a one-off slug that
no other receipt from that chain will ever match.
"""

import re

# (chain key, patterns matched as whole words against the upper-cased header)
_CHAINS: list[tuple[str, tuple[str, ...]]] = [
    (
        "s-group",
        (
            "S-GROUP",
            "S-KAUPAT",
            "PRISMA",
            "S-MARKET",
            "ALEPA",
            "SALE",
            "HOK-ELANTO",
            "SOK",
        ),
    ),
    (
        "k-group",
        ("K-GROUP", "K-MARKET", "K-CITYMARKET", "K-SUPERMARKET", "K-RUOKA", "KESKO"),
    ),
    ("lidl", ("LIDL",)),
    ("tokmanni", ("TOKMANNI",)),
]

# The chain keys `normalize_store_chain` can return besides a slug (used by callers that need
# to tell "a recognised chain" from "we gave up and slugged it", e.g. the rekey script).
CHAIN_KEYS: frozenset[str] = frozenset(key for key, _ in _CHAINS)

# Only the start of the header is checked: a multi-page or very noisy OCR read can accidentally
# contain a chain's name further down, and callers only ever hand this function the header
# anyway (a single line from the heuristic parser, or the extraction's short store field).
_HEADER_LINES = 3
_HEADER_CHARS = 60

# A pattern this short is too short to risk a generic one-edit fuzzy match (too many ordinary
# words are one edit away from a 3-letter string); it is only ever matched exactly.
_MIN_FUZZY_PATTERN_LEN = 4
# Above this length a single edit of any kind (insert/delete/substitute/adjacent-transpose) is
# allowed, since a real chain pattern is distinctive enough that one edit rarely collides with
# an unrelated word.
_GENERIC_FUZZY_MIN_LEN = 5

# OCR confusion pairs: glyphs that look alike and get misread for one another. A 4-character
# pattern (too short for the generic rule above) is only allowed a fuzzy match when the single
# edit between the token and the pattern is exactly one of these confusions. Each tuple is
# (canonical form, confused form); normalising both sides to the canonical form and comparing
# for equality accepts a confusion-only edit (including a length-changing one like rn/m) while
# rejecting any other single edit.
_OCR_CONFUSIONS: tuple[tuple[str, str], ...] = (
    (
        "L",
        "I",
    ),  # lowercase l / i look alike, especially after upscaling a thermal receipt
    ("L", "1"),  # l / digit 1
    ("O", "0"),  # letter O / digit 0
    ("M", "RN"),  # m is often split into two strokes read as rn
)


def _header_window(raw: str) -> str:
    lines = raw.splitlines()[:_HEADER_LINES]
    return "\n".join(lines)[:_HEADER_CHARS]


def _damerau_levenshtein(a: str, b: str) -> int:
    """Optimal-string-alignment edit distance: insert, delete, substitute or adjacent-transpose.

    Each operation costs 1. This is the restricted (OSA) variant rather than true Damerau-
    Levenshtein, which only differs from it when more than one transposition overlaps - never
    the case at the distance-of-1 threshold this module checks for.
    """
    if a == b:
        return 0
    la, lb = len(a), len(b)
    prev_prev = [0] * (lb + 1)
    prev = list(range(lb + 1))
    curr = [0] * (lb + 1)
    for i in range(1, la + 1):
        curr[0] = i
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                curr[j] = min(curr[j], prev_prev[j - 2] + 1)  # adjacent transposition
        prev_prev, prev, curr = prev, curr, prev_prev
    return prev[lb]


def _confusion_normalise(token: str) -> str:
    """Collapse known OCR confusions to their canonical form for an equality check."""
    for canonical, confused in _OCR_CONFUSIONS:
        token = token.replace(confused, canonical)
    return token


def _fuzzy_match(token: str, pattern: str) -> bool:
    if len(pattern) < _MIN_FUZZY_PATTERN_LEN:
        return False
    if len(pattern) >= _GENERIC_FUZZY_MIN_LEN:
        return _damerau_levenshtein(token, pattern) <= 1
    # Exactly `_MIN_FUZZY_PATTERN_LEN` characters: only a known OCR confusion earns the fuzzy
    # match. Normalising both sides and requiring equality accepts only an edit that is itself
    # one of the confusions (any other single edit leaves a difference after normalising).
    return _confusion_normalise(token) == _confusion_normalise(pattern)


def normalize_store_chain(raw: str | None) -> str | None:
    """Chain key such as ``s-group``; other stores become a lower-case slug; empty is None."""
    if raw is None or not raw.strip():
        return None
    header = _header_window(raw)
    text = header.upper()
    for key, patterns in _CHAINS:
        for pattern in patterns:
            if re.search(rf"(?<![\w-]){re.escape(pattern)}(?![\w-])", text):
                return key
    tokens = [token for token in text.split() if len(token) >= 2]
    for key, patterns in _CHAINS:
        for pattern in patterns:
            for token in tokens:
                if _fuzzy_match(token, pattern):
                    return key
    slug = re.sub(r"[^\w]+", "-", raw.strip().lower()).strip("-")
    return slug or None
