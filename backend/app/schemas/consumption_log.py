from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ConsumptionLogBase(BaseModel):
    """Base consumption log schema with common fields."""

    inventory_item_id: UUID = Field(..., description="Inventory item ID")
    product_master_id: UUID = Field(..., description="Product master ID")
    action: str = Field(..., description="Action: use_partial, use_full, discard, adjust")
    quantity_consumed: Decimal = Field(..., gt=0, description="Quantity consumed")
    consumption_context: str | None = Field(
        None, description="Context: breakfast, lunch, dinner, snack, cooking"
    )


class ConsumptionLogCreate(ConsumptionLogBase):
    """Schema for creating a new consumption log entry."""

    pass


class ConsumptionLogUpdate(BaseModel):
    """Schema for updating a consumption log entry."""

    action: str | None = None
    quantity_consumed: Decimal | None = Field(None, gt=0)
    consumption_context: str | None = None


class ConsumptionLogResponse(ConsumptionLogBase):
    """Schema for consumption log API responses."""

    id: UUID
    logged_at: datetime

    model_config = {"from_attributes": True}
