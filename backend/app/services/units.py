"""Canonical quantity units.

Operator ruling (DEC-1): quantities are stored in ``dl | tsp | tbsp | g | pcs``. Receipt and
barcode data arrive in other units and are converted here, in one place.
"""

from typing import Literal

CanonicalUnit = Literal["g", "dl", "pcs"]

# unit alias -> (factor, canonical unit)
_CONVERSIONS: dict[str, tuple[float, CanonicalUnit]] = {
    "kg": (1000.0, "g"),
    "g": (1.0, "g"),
    "l": (10.0, "dl"),
    "dl": (1.0, "dl"),
    "cl": (0.1, "dl"),
    "ml": (0.01, "dl"),
    "pcs": (1.0, "pcs"),
    "kpl": (1.0, "pcs"),
    "unit": (1.0, "pcs"),
    "st": (1.0, "pcs"),
}


def to_canonical(value: float, unit: str) -> tuple[float, CanonicalUnit]:
    """Convert ``value`` in ``unit`` to a canonical unit, rounded to two decimals.

    Raises:
        ValueError: The unit is not a known weight, volume or count unit.
    """
    key = unit.strip().lower()
    if key not in _CONVERSIONS:
        raise ValueError(f"Unknown unit: {unit!r}")
    factor, canonical = _CONVERSIONS[key]
    return round(float(value) * factor, 2), canonical


def receipt_line_quantity(
    quantity: float | None, weight_kg: float | None
) -> tuple[float, CanonicalUnit]:
    """Quantity of one receipt line: grams when a weight line was read, otherwise pieces.

    Pack sizes printed in product names (``GLÖGI 1L``) are deliberately not parsed here; a
    line bought as ``2 KPL`` is 2 pieces (operator ruling, MVP-R1b).
    """
    if weight_kg is not None:
        return to_canonical(weight_kg, "kg")
    return to_canonical(quantity or 1, "pcs")
