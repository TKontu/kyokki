"""Shared Pydantic field types and validators."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

from app.services.units import canonical_factor, to_canonical_decimal

# DEC-2: Decimal quantities travel as JSON numbers. Validation and Python-side values stay
# Decimal; only JSON output is converted.
JsonDecimal = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]


def canonicalize_units(
    model: BaseModel, unit_field: str, amount_fields: Sequence[str]
) -> str | None:
    """Convert-on-write (MVP-U1): rewrite ``unit_field`` to its canonical unit and scale the
    amount fields that were provided. Returns the canonical unit, or None when no unit was set.

    Only fields the client actually sent are touched, so partial updates stay partial.

    Raises:
        ValueError: Unknown unit (FastAPI turns it into a 422).
    """
    unit = getattr(model, unit_field)
    if unit is None:
        return None
    _, canonical = canonical_factor(unit)
    for name in amount_fields:
        if name in model.model_fields_set:
            setattr(model, name, to_canonical_decimal(getattr(model, name), unit))
    setattr(model, unit_field, canonical)
    return canonical
