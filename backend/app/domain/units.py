"""Canonical quantity units.

Operator ruling (DEC-1): quantities are stored in ``dl | tsp | tbsp | g | pcs``. Everything that
arrives in another unit (receipts, barcode data, API requests) is converted here, in one place.
``tsp`` and ``tbsp`` are canonical in their own right and are not converted to dl (MVP-U1).
"""

import re
from decimal import ROUND_HALF_UP, Decimal
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


def quantise(value: Decimal | float) -> Decimal:
    """An amount at the precision the columns actually store, `Numeric(10, 2)`.

    Used by consume so the arithmetic matches what is written back (H23): a third of a
    0.01 dl remainder is not a helping, and a consume that rounds away to nothing is refused
    rather than logged as something that happened.
    """
    return Decimal(str(value)).quantize(_CENT)


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


# A size printed in the product name: SIPULI 500G, PORKKANA 1KG, NACHO CHIPS 475G.
# Grams and kilograms only - COOP ROSKAPUSSI 30L is not a weight, and a litre of
# glogi belongs in dl. The negative lookahead keeps 25KPL from reading as 25 kg.
_SIZE_IN_NAME = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(KG|G)(?![A-Z])", re.IGNORECASE
)


def grams_from_name(name: str | None) -> float | None:
    """The pack weight a receipt printed in the product name, or None.

    The model is not asked for this. It was offered a `pk` field and answered on 1 line
    of 49 while dragging the other estimates down with it (Q8,
    docs/vLLM_MANUAL_TEST.md), so the pack weight comes from the name when the shop
    prints it and from the cook otherwise.
    """
    if not name:
        return None
    match = _SIZE_IN_NAME.search(name)
    if match is None:
        return None
    amount = Decimal(match.group(1).replace(",", "."))
    grams = amount * 1000 if match.group(2).upper() == "KG" else amount
    return float(grams) if grams > 0 else None


def pieces_to_grams(
    pieces: Decimal | float | None, pack_grams: Decimal | float | None
) -> float | None:
    """What a counted line weighs, or ``None`` when that cannot be said.

    The mirror of `grams_to_pieces` (Q8). A receipt counts packs of mince; the cook
    wants to know there is 400 g in the freezer. Unlike pieces, the result is not
    rounded to a whole anything - grams are already the fine-grained unit.
    """
    if pieces is None or pack_grams is None:
        return None
    count, per_pack = Decimal(str(pieces)), Decimal(str(pack_grams))
    if count <= 0 or per_pack <= 0:
        return None
    return float(count * per_pack)


def grams_to_pieces(
    grams: Decimal | float | None, piece_grams: Decimal | float | None
) -> int | None:
    """How many whole pieces a weighed line is, or ``None`` when that cannot be said.

    A receipt prices apples by the kilo; the cook eats them one at a time (Q2). The estimate
    is deliberately rough - the point is that stock reads "9 apples" rather than "1072 g" - and
    it never rounds a real purchase down to nothing.
    """
    if grams is None or piece_grams is None:
        return None
    weight, per_piece = Decimal(str(grams)), Decimal(str(piece_grams))
    if per_piece <= 0 or weight <= 0:
        return None
    return max(1, int((weight / per_piece).to_integral_value(rounding=ROUND_HALF_UP)))
