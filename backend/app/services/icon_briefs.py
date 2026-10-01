"""Operator icon briefs for the Q18-G2 generation gap.

The gap list (`docs/spikes/Q18_exact_emoji.md`, "Icon briefs from the operator") has four
products where the operator described what the generated icon should look like, because the
closest obvious picture is wrong: a fresh tomato is not canned tomatoes, and a generic fish is
not fish fingers. Every other gap product's subject is just its own generic name.

This is its own small file, separate from `product_emoji.py`'s curated table (a sibling lane's
file, `app/resources/emoji_curated.json`) - the two can change independently, and this is the
only place `services/product_icons.py` builds its generation subject text from.
"""

from app.services.product_names import normalize_product_name

# Sourced verbatim from the gap list's briefs table.
_BRIEFS: dict[str, str] = {
    "Tomato puree": "a small can or squeeze-out tube",
    "Canned tomatoes": "a can, not a fresh tomato",
    "Canned tuna": "the tuna can as sold",
    "Fish fingers": "the fish fingers, or their pack, as sold",
}

BRIEFS: dict[str, str] = {
    normalize_product_name(name): brief for name, brief in _BRIEFS.items()
}


def brief_for(generic_name: str) -> str | None:
    """The operator's own words for this gap product's icon, if any were given."""
    return BRIEFS.get(normalize_product_name(generic_name))
