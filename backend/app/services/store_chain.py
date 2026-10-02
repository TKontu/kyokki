"""Normalise store header text to a stable chain key.

The extraction model reads whatever the header says (``S-KAUPAT``, ``Prisma ruoan
verkkokauppa``, ``K-Citymarket Ruoholahti``). Store aliases are scoped by chain, so every
variant of the same chain must map to one key.

OCR sometimes misreads the chain word itself (``Lidi Suomi Ky`` for a Lidl receipt), or reads a
chain's hyphen as a plain space (``K Citymarket`` for ``K-Citymarket``). After the exact pass
over the raw header fails, a second exact pass tries joining adjacent header words with a
hyphen, and then a fuzzy pass tolerates one edit between a header word (or hyphen-joined pair)
and a known pattern - but only an edit that is itself a known OCR confusion, or, for a long
enough pattern, a plain insertion/deletion/transposition. This way the receipt still lands on
the real chain instead of inventing a one-off slug that no other receipt from that chain will
ever match, without an ordinary word one edit away from a short pattern false-positiving.

Only the first few lines of the header count (`_header_window`), for both passes: every caller
hands this function a short header - a single line from the heuristic parser, or the
extraction's short store field - never the whole receipt body, so a word that merely turns up
somewhere later in a long OCR read is never in scope.
"""

import re
from dataclasses import dataclass

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

# A pattern this short is too short to risk a fuzzy match on its own (too many ordinary words
# are one edit away from a 3-letter string); it is only ever matched exactly.
_MIN_FUZZY_PATTERN_LEN = 4
# A plain insertion, deletion or adjacent-transposition (anything that is not itself a known
# OCR confusion) is only accepted for a pattern at least this long: a real chain pattern that
# long is distinctive enough that one such edit rarely collides with an unrelated word. Shorter
# patterns - including the 4-character ones - only ever match through `_OCR_CONFUSIONS` below.
_INDEL_TRANSPOSE_MIN_LEN = 7

# OCR confusion pairs: glyphs that look alike and get misread for one another. A *substitution*
# only ever counts as a fuzzy match when it is exactly one of these (never a generic "any
# substitution" rule - two ordinary words a single unrelated letter apart must not collide with
# a chain pattern). Each tuple is two interchangeable spellings of the same glyph(s); either can
# turn up in the header where the other appears in the pattern, and one may be longer than the
# other (``rn``/``m`` and the like), which is why this is substring replacement rather than a
# same-length character swap.
_OCR_CONFUSIONS: tuple[tuple[str, str], ...] = (
    (
        "L",
        "I",
    ),  # lowercase l / i look alike, especially after upscaling a thermal receipt
    ("L", "1"),  # l / digit 1
    ("O", "0"),  # letter O / digit 0
    ("M", "RN"),  # m is often split into two strokes read as rn
    ("M", "N"),  # m / n
    ("S", "5"),  # s / digit 5
    ("B", "8"),  # b / digit 8
    ("D", "CL"),  # d is sometimes split into two strokes read as cl
    ("W", "VV"),  # w is sometimes split into two strokes read as vv
)


@dataclass(frozen=True)
class ChainMatch:
    """A chain key `normalize_store_chain` found, and how it found it.

    `rule` is ``"exact"`` (the pattern, or a hyphen-rejoin of two adjacent header words, is
    exactly a known pattern) or ``"fuzzy"`` (one tolerated edit away). `token` is the header
    word, or hyphen-joined pair of words, that matched. Exposed for callers that need to tell
    a genuine OCR fix from an exact match that is suspicious precisely because it needed no
    tolerance at all - see `scripts/rekey_store_chains.py`.
    """

    key: str
    rule: str
    token: str


def _header_window(raw: str) -> str:
    lines = raw.splitlines()[:_HEADER_LINES]
    return "\n".join(lines)[:_HEADER_CHARS]


def _confusion_variants(s: str) -> set[str]:
    """Every string reachable from `s` by swapping exactly one OCR confusion in it."""
    variants: set[str] = set()
    for form_a, form_b in _OCR_CONFUSIONS:
        for needle, replacement in ((form_a, form_b), (form_b, form_a)):
            start = 0
            while (idx := s.find(needle, start)) != -1:
                variants.add(s[:idx] + replacement + s[idx + len(needle) :])
                start = idx + 1
    return variants


def _confusion_substitution_match(token: str, pattern: str) -> bool:
    """True if `token` and `pattern` differ by exactly one OCR confusion, nothing else.

    Checking string equality after swapping exactly one occurrence (rather than normalising
    both sides and comparing) is what makes this exactly one edit: normalising would also
    accept two confusions at once (each individually valid, but never allowed together).
    """
    return pattern in _confusion_variants(token)


def _is_single_indel(short: str, long_: str) -> bool:
    """True if `long_` is `short` with exactly one character inserted somewhere."""
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long_):
        if short[i] == long_[j]:
            i += 1
            j += 1
            continue
        if skipped:
            return False
        skipped = True
        j += 1
    return True


def _edit_kind(a: str, b: str) -> str | None:
    """Classify the single edit turning `a` into `b`, or None if that is not possible.

    One of ``"substitution"``, ``"transposition"`` (same length) or ``"indel"`` (lengths a
    single character apart). None covers both "identical" and "more than one edit apart".
    """
    if a == b:
        return None
    la, lb = len(a), len(b)
    if la == lb:
        diffs = [i for i in range(la) if a[i] != b[i]]
        if len(diffs) == 1:
            return "substitution"
        if (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and a[diffs[0]] == b[diffs[1]]
            and a[diffs[1]] == b[diffs[0]]
        ):
            return "transposition"
        return None
    if abs(la - lb) == 1:
        short, long_ = (a, b) if la < lb else (b, a)
        if _is_single_indel(short, long_):
            return "indel"
    return None


def _fuzzy_match(token: str, pattern: str) -> bool:
    if len(pattern) < _MIN_FUZZY_PATTERN_LEN:
        return False
    if _confusion_substitution_match(token, pattern):
        return True
    if len(pattern) < _INDEL_TRANSPOSE_MIN_LEN:
        return False
    # A plain substitution never reaches here as anything but "no match": it already had its
    # one chance, as a confusion, just above. Only insertion/deletion/transposition count now.
    return _edit_kind(token, pattern) in ("transposition", "indel")


def _joined_pairs(tokens: list[str]) -> list[str]:
    """Adjacent header words joined with a hyphen, in case OCR read it as a plain space."""
    return [f"{tokens[i]}-{tokens[i + 1]}" for i in range(len(tokens) - 1)]


def match_chain(raw: str | None) -> ChainMatch | None:
    """The chain `normalize_store_chain` would find, and how - None if it would slug instead."""
    if raw is None or not raw.strip():
        return None
    text = _header_window(raw).upper()
    for key, patterns in _CHAINS:
        for pattern in patterns:
            if re.search(rf"(?<![\w-]){re.escape(pattern)}(?![\w-])", text):
                return ChainMatch(key=key, rule="exact", token=pattern)

    all_tokens = text.split()
    joined = _joined_pairs(all_tokens)

    # A second exact pass: two adjacent words rejoined with a hyphen, in case OCR printed the
    # pattern's hyphen as a space ("K Citymarket" for "K-Citymarket").
    for key, patterns in _CHAINS:
        for pattern in patterns:
            if pattern in joined:
                return ChainMatch(key=key, rule="exact", token=pattern)

    fuzzy_candidates = [token for token in all_tokens if len(token) >= 2] + joined
    for key, patterns in _CHAINS:
        for pattern in patterns:
            for candidate in fuzzy_candidates:
                if _fuzzy_match(candidate, pattern):
                    return ChainMatch(key=key, rule="fuzzy", token=candidate)
    return None


def normalize_store_chain(raw: str | None) -> str | None:
    """Chain key such as ``s-group``; other stores become a lower-case slug; empty is None."""
    if raw is None or not raw.strip():
        return None
    match = match_chain(raw)
    if match is not None:
        return match.key
    slug = re.sub(r"[^\w]+", "-", raw.strip().lower()).strip("-")
    return slug or None
