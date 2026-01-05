from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class InventoryItemBase(BaseModel):
    """Base inventory item schema with common fields."""

    product_master_id: UUID = Field(..., description="Product master ID")
    receipt_id: UUID | None = Field(None, description="Source receipt ID")
    initial_quantity: Decimal = Field(..., gt=0, description="Initial quantity")
    current_quantity: Decimal = Field(..., ge=0, description="Current quantity")
    unit: str = Field(..., description="Unit: ml, g, pcs, unit")
    status: str = Field("sealed", description="Status: sealed, opened, partial, empty, discarded")
    purchase_date: date | None = Field(None, description="Purchase date")
    expiry_date: date = Field(..., description="Expiry date")
    expiry_source: str = Field("calculated", description="Expiry source: scanned, calculated, manual")
    opened_date: date | None = Field(None, description="Date when opened")
    batch_number: str | None = Field(None, description="Batch number from GS1 DataMatrix")
    location: str = Field("main_fridge", description="Location: main_fridge, freezer, pantry")
    notes: str | None = Field(None, description="User notes")


class InventoryItemCreate(InventoryItemBase):
    """Schema for creating a new inventory item."""

    pass


class InventoryItemUpdate(BaseModel):
    """Schema for updating an inventory item."""

    current_quantity: Decimal | None = Field(None, ge=0)
    status: str | None = None
    expiry_date: date | None = None
    expiry_source: str | None = None
    opened_date: date | None = None
    location: str | None = None
    notes: str | None = None


class InventoryItemResponse(InventoryItemBase):
    """Schema for inventory item API responses."""

    id: UUID
    created_at: datetime
    consumed_at: datetime | None = None

    model_config = {"from_attributes": True}
