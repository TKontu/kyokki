from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.types import JsonDecimal, canonicalize_units


class InventoryItemBase(BaseModel):
    """Base inventory item schema with common fields."""

    product_master_id: UUID = Field(..., description="Product master ID")
    receipt_id: UUID | None = Field(None, description="Source receipt ID")
    initial_quantity: JsonDecimal = Field(..., gt=0, description="Initial quantity")
    current_quantity: JsonDecimal = Field(..., ge=0, description="Current quantity")
    unit: str = Field(
        ..., description="Unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    status: str = Field(
        "sealed", description="Status: sealed, opened, partial, empty, discarded"
    )
    purchase_date: date | None = Field(None, description="Purchase date")
    expiry_date: date = Field(..., description="Expiry date")
    expiry_source: str = Field(
        "calculated", description="Expiry source: scanned, calculated, manual"
    )
    opened_date: date | None = Field(None, description="Date when opened")
    batch_number: str | None = Field(
        None, description="Batch number from GS1 DataMatrix"
    )
    location: str = Field(
        "main_fridge", description="Location: main_fridge, freezer, pantry"
    )
    notes: str | None = Field(None, description="User notes")


class InventoryItemCreate(InventoryItemBase):
    """Schema for creating a new inventory item."""

    @model_validator(mode="after")
    def canonical_units(self) -> "InventoryItemCreate":
        canonicalize_units(self, "unit", ["initial_quantity", "current_quantity"])
        return self


class InventoryItemUpdate(BaseModel):
    """Schema for updating an inventory item."""

    current_quantity: JsonDecimal | None = Field(None, ge=0)
    status: str | None = None
    expiry_date: date | None = None
    expiry_source: str | None = None
    opened_date: date | None = None
    location: str | None = None
    notes: str | None = None


class InventoryItemResponse(InventoryItemBase):
    """Schema for inventory item API responses."""

    id: UUID
    product_name: str = Field(..., description="Product canonical name")
    category: str = Field(..., description="Category ID, e.g. dairy")
    category_name: str = Field(..., description="Category display name")
    category_icon: str | None = Field(None, description="Category emoji icon")
    created_at: datetime
    consumed_at: datetime | None = None

    model_config = {"from_attributes": True}
