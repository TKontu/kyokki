from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.types import JsonDecimal, canonicalize_units


class ShoppingPriority(StrEnum):
    """How badly it is needed."""

    URGENT = "urgent"
    NORMAL = "normal"
    LOW = "low"


class ShoppingSource(StrEnum):
    """Why the line is on the list - who or what put it there."""

    MANUAL = "manual"
    AUTO_RESTOCK = "auto_restock"
    RECIPE = "recipe"


class ShoppingListItemBase(BaseModel):
    """Base shopping list item schema with common fields."""

    product_master_id: UUID | None = Field(
        None, description="Product master ID (null for free-text items)"
    )
    name: str = Field(..., description="Display name")
    quantity: JsonDecimal = Field(..., gt=0, description="Quantity to purchase")
    unit: str = Field(
        ..., description="Unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    priority: ShoppingPriority = Field(
        ShoppingPriority.NORMAL, description="How badly it is needed"
    )
    source: ShoppingSource = Field(
        ShoppingSource.MANUAL, description="Why the line is on the list"
    )


class ShoppingListItemCreate(ShoppingListItemBase):
    """Schema for creating a new shopping list item."""

    @model_validator(mode="after")
    def canonical_units(self) -> "ShoppingListItemCreate":
        canonicalize_units(self, "unit", ["quantity"])
        return self


class ShoppingListItemUpdate(BaseModel):
    """Schema for updating a shopping list item."""

    product_master_id: UUID | None = None
    name: str | None = None
    quantity: JsonDecimal | None = Field(None, gt=0)
    unit: str | None = None
    priority: ShoppingPriority | None = None
    is_purchased: bool | None = None

    @model_validator(mode="after")
    def canonical_units(self) -> "ShoppingListItemUpdate":
        canonicalize_units(self, "unit", ["quantity"])
        return self


class ShoppingListItemResponse(ShoppingListItemBase):
    """Schema for shopping list item API responses."""

    id: UUID
    is_purchased: bool
    added_at: datetime
    purchased_at: datetime | None = None

    model_config = {"from_attributes": True}
