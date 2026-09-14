"""Canonical quantity units.

Operator ruling (DEC-1): quantities are stored in ``dl | tsp | tbsp | g | pcs``. Everything that
arrives in another unit (receipts, barcode data, API requests) is converted here, in one place.
``tsp`` and ``tbsp`` are canonical in their own right and are not converted to dl (MVP-U1).
"""

from decimal import Decimal
from typing import Literal

CanonicalUnit = Literal["dl", "tsp", "tbsp", "g", "pcs"]
UnitType = Literal["volume", "weight", "count"]

_CENT = Decimal("0.01")

# unit alias -> (factor, canonical unit)
_CONVERSIONS: dict[str, tuple[Decimal, CanonicalUnit]] = {
    "kg": (Decimal("1000"), "g"),
    "g": (Decimal("1"), "g"),
    "l": (Decimal("10"), "dl"),
    "dl": (Decimal("1"), "dl"),
    "cl": (Decimal("0.1"), "dl"),
    "ml": (Decimal("0.01"), "dl"),
    "tsp": (Decimal("1"), "tsp"),
    "tbsp": (Decimal("1"), "tbsp"),
    "pcs": (Decimal("1"), "pcs"),
    "kpl": (Decimal("1"), "pcs"),
    "unit": (Decimal("1"), "pcs"),
    "st": (Decimal("1"), "pcs"),
}

_UNIT_TYPES: dict[CanonicalUnit, UnitType] = {
    "dl": "volume",
    "tsp": "volume",
    "tbsp": "volume",
    "g": "weight",
    "pcs": "count",
}


def canonical_factor(unit: str) -> tuple[Decimal, CanonicalUnit]:
    """Multiplier and canonical unit for ``unit`` (case and whitespace insensitive).

    Raises:
        ValueError: The unit is not a known weight, volume or count unit.
    """
    key = unit.strip().lower()
    if key not in _CONVERSIONS:
        raise ValueError(f"Unknown unit: {unit!r}")
    return _CONVERSIONS[key]


def to_canonical_decimal(value: Decimal | None, unit: str) -> Decimal | None:
    """Convert an amount to the canonical unit of ``unit``, quantized like Numeric(10, 2)."""
    factor, _ = canonical_factor(unit)
    if value is None:
        return None
    return (Decimal(value) * factor).quantize(_CENT)


def to_canonical(value: float, unit: str) -> tuple[float, CanonicalUnit]:
    """Float variant for receipt quantities: ``(converted value, canonical unit)``."""
    factor, canonical = canonical_factor(unit)
    return round(float(Decimal(str(value)) * factor), 2), canonical


def unit_type_for(unit: str) -> UnitType:
    """volume, weight or count for any known unit."""
    return _UNIT_TYPES[canonical_factor(unit)[1]]


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
