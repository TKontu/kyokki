from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ShoppingListItemBase(BaseModel):
    """Base shopping list item schema with common fields."""

    product_master_id: UUID | None = Field(None, description="Product master ID (null for free-text items)")
    name: str = Field(..., description="Display name")
    quantity: Decimal = Field(..., gt=0, description="Quantity to purchase")
    unit: str = Field(..., description="Unit: ml, g, pcs, unit")
    priority: str = Field("normal", description="Priority: urgent, normal, low")
    source: str = Field("manual", description="Source: manual, auto_restock, recipe")


class ShoppingListItemCreate(ShoppingListItemBase):
    """Schema for creating a new shopping list item."""

    pass


class ShoppingListItemUpdate(BaseModel):
    """Schema for updating a shopping list item."""

    product_master_id: UUID | None = None
    name: str | None = None
    quantity: Decimal | None = Field(None, gt=0)
    unit: str | None = None
    priority: str | None = None
    is_purchased: bool | None = None


class ShoppingListItemResponse(ShoppingListItemBase):
    """Schema for shopping list item API responses."""

    id: UUID
    is_purchased: bool
    added_at: datetime
    purchased_at: datetime | None = None

    model_config = {"from_attributes": True}
