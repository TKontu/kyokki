"""Request and response shapes for the Home Assistant REST endpoints (docs/HOME_ASSISTANT_SPEC.md).

Phase 1 only: five routes behind AG1's bearer auth, reusing AG2's stock-by-name and AG6's
low-stock logic. These shapes are HA's own (not the agent API's): numbers and strings a REST
sensor or a voice intent can use directly, not the richer agent shapes.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.types import JsonDecimal, canonicalize_units
from app.services.units import canonical_factor


class HaStatusResponse(BaseModel):
    """`GET /api/ha/status`: one call, several sensors. Active items only."""

    total_items: int
    expiring_within_3_days: int
    expired: int
    by_location: dict[str, int]
    last_updated: datetime


class HaExpiringItem(BaseModel):
    id: UUID
    name: str
    category: str
    expiry_date: date
    days_until_expiry: int = Field(
        ..., description="Negative when the item has already expired"
    )
    quantity_percent: int = Field(
        ..., description="current_quantity / initial_quantity"
    )


class HaExpiringResponse(BaseModel):
    """`GET /api/ha/expiring`: soonest first, truncated to `limit`."""

    items: list[HaExpiringItem]
    count: int


class HaLowStockItem(BaseModel):
    id: UUID
    name: str
    category: str
    quantity_percent: int = Field(..., description="on_hand / min_stock_quantity")
    on_shopping_list: bool


class HaLowStockResponse(BaseModel):
    """`GET /api/ha/low-stock`: read-only; never writes to the shopping list."""

    items: list[HaLowStockItem]
    count: int


class HaConsumeRequest(BaseModel):
    """`POST /api/ha/consume`: by product name, amount and unit (the agent's `stock consume`,
    not the original spec's fuzzy words)."""

    name: str = Field(
        ..., min_length=1, description="Canonical or learned product name"
    )
    amount: JsonDecimal = Field(..., gt=0)
    unit: str = Field(
        ..., description="dl, tsp, tbsp, g, pcs, or one converting to them"
    )

    @field_validator("name")
    @classmethod
    def not_blank(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("name must not be blank")
        return name

    @field_validator("unit")
    @classmethod
    def known_unit(cls, unit: str) -> str:
        canonical_factor(unit)  # raises ValueError -> 422
        return unit


class HaConsumedItem(BaseModel):
    name: str
    quantity_before: JsonDecimal
    quantity_after: JsonDecimal


class HaConsumeResponse(BaseModel):
    success: bool = True
    item: HaConsumedItem


class HaShoppingAddRequest(BaseModel):
    """`POST /api/ha/shopping/add`: by name, with an optional amount and unit (1 pcs)."""

    name: str = Field(..., min_length=1)
    amount: JsonDecimal = Field(Decimal(1), gt=0)
    unit: str = Field("pcs")

    @field_validator("name")
    @classmethod
    def not_blank(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("name must not be blank")
        return name

    @model_validator(mode="after")
    def canonical_units(self) -> "HaShoppingAddRequest":
        canonicalize_units(self, "unit", ["amount"])
        return self
