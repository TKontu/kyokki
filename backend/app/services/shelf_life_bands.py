"""How long a shelf life may plausibly be, by category.

The catalog estimate uses these to reject a confident wrong answer (Q11), and the products
page uses them to flag a number at the edge of its category's range (H58). Kept apart from
`catalog_estimates` so the category schema can read them without importing the model client.
"""

# What a shelf life may plausibly be, in days, by the kind of thing it is. The model is
# asked for a number and sometimes answers with a confident wrong one; a band is cheaper
# than trusting it, and this writes to the whole catalog at once. Anything outside its
# category's band is dropped rather than clamped - a rejected answer leaves the
# placeholder in place, which is where it already was.
PLAUSIBLE_DAYS: dict[str, tuple[int, int]] = {
    "meat": (1, 60),
    "fish": (1, 30),
    "dairy": (2, 120),
    "cheese": (5, 365),
    "produce": (2, 120),
    "fruits": (2, 120),
    "bread": (2, 800),
    "ready_meals": (1, 21),
    "frozen": (30, 730),
    "pantry": (7, 1825),
    "beverages": (7, 1825),
    "condiments": (7, 1825),
    "snacks": (7, 730),
}
# A category nobody listed above still gets a sanity check, just a loose one.
DEFAULT_BAND = (1, 1825)


def band_for(category_id: str | None) -> tuple[int, int]:
    """The (shortest, longest) plausible shelf life in days for a category."""
    return PLAUSIBLE_DAYS.get(category_id or "", DEFAULT_BAND)
