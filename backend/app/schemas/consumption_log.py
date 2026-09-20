from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.types import JsonDecimal


class ConsumptionAction(StrEnum):
    """What happened to the food, as recorded rather than as decided.

    The distinction this whole column exists for is `discard` against the two `use_` values:
    thrown away is waste, eaten is not, and reducing waste is the point of the app. Nothing
    reads the log back yet - that is H46.

    `ADJUST` is declared and never written: a correction is deliberately not consumption
    (`crud/inventory_item.update_inventory_item`). H46 decides whether it should be.
    """

    USE_PARTIAL = "use_partial"
    USE_FULL = "use_full"
    DISCARD = "discard"
    ADJUST = "adjust"


class ConsumptionLogBase(BaseModel):
    """Base consumption log schema with common fields."""

    inventory_item_id: UUID = Field(..., description="Inventory item ID")
    product_master_id: UUID = Field(..., description="Product master ID")
    action: ConsumptionAction = Field(..., description="What happened to the food")
    quantity_consumed: JsonDecimal = Field(..., gt=0, description="Quantity consumed")
    consumption_context: str | None = Field(
        None, description="Context: breakfast, lunch, dinner, snack, cooking"
    )


class ConsumptionLogCreate(ConsumptionLogBase):
    """Schema for creating a new consumption log entry."""

    pass


class ConsumptionLogUpdate(BaseModel):
    """Schema for updating a consumption log entry."""

    action: str | None = None
    quantity_consumed: JsonDecimal | None = Field(None, gt=0)
    consumption_context: str | None = None


class ConsumptionLogResponse(ConsumptionLogBase):
    """Schema for consumption log API responses."""

    id: UUID
    logged_at: datetime

    model_config = {"from_attributes": True}
