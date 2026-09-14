"""Normalise store header text to a stable chain key.

The extraction model reads whatever the header says (``S-KAUPAT``, ``Prisma ruoan
verkkokauppa``, ``K-Citymarket Ruoholahti``). Store aliases are scoped by chain, so every
variant of the same chain must map to one key.
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


def normalize_store_chain(raw: str | None) -> str | None:
    """Chain key such as ``s-group``; other stores become a lower-case slug; empty is None."""
    if raw is None or not raw.strip():
        return None
    text = raw.upper()
    for key, patterns in _CHAINS:
        for pattern in patterns:
            if re.search(rf"(?<![\w-]){re.escape(pattern)}(?![\w-])", text):
                return key
    slug = re.sub(r"[^\w]+", "-", raw.strip().lower()).strip("-")
    return slug or None
