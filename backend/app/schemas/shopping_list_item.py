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


class ShoppingGenerateRequest(BaseModel):
    """What to build a shopping list from (AG6). Only ``low_stock`` exists for now.

    An empty or unknown source is refused by the service as 400 ``invalid``, not here,
    so an agent gets the stable error shape rather than a 422.
    """

    sources: list[str] = Field(
        ..., description="low_stock: every product below its min_stock_quantity"
    )
    dry_run: bool = Field(False, description="Plan only; nothing is written")


class ShoppingGenerateLine(BaseModel):
    """One product the generator looked at, and what came of it.

    ``need``, ``on_hand`` and ``min_stock`` are in ``unit``, the product's own unit.
    ``item_id`` is the list item added, raised or left alone (none on a dry run's added
    lines). A skipped line has no ``need`` or ``on_hand`` and says why in ``reason``.
    """

    product_id: UUID
    name: str
    need: JsonDecimal | None = None
    unit: str
    on_hand: JsonDecimal | None = None
    min_stock: JsonDecimal
    item_id: UUID | None = None
    reason: str | None = None


class ShoppingGenerateResponse(BaseModel):
    """added: new list items. updated: open items raised to the need. unchanged: open
    items already big enough. skipped: products whose stock could not be counted."""

    added: list[ShoppingGenerateLine] = Field(default_factory=list)
    updated: list[ShoppingGenerateLine] = Field(default_factory=list)
    unchanged: list[ShoppingGenerateLine] = Field(default_factory=list)
    skipped: list[ShoppingGenerateLine] = Field(default_factory=list)
    dry_run: bool
