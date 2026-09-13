"""Shared Pydantic field types."""

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# DEC-2: Decimal quantities travel as JSON numbers. Validation and Python-side values stay
# Decimal; only JSON output is converted.
JsonDecimal = Annotated[
    Decimal, PlainSerializer(float, return_type=float, when_used="json")
]
