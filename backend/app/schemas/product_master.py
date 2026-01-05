from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ProductMasterBase(BaseModel):
    """Base product master schema with common fields."""

    canonical_name: str = Field(..., description="Canonical product name")
    category: str = Field(..., description="Product category ID")
    storage_type: str = Field(..., description="Storage type: refrigerator, freezer, pantry")
    default_shelf_life_days: int = Field(..., gt=0, description="Default shelf life (unopened)")
    opened_shelf_life_days: int | None = Field(None, gt=0, description="Shelf life after opening")
    unit_type: str = Field(..., description="Unit type: volume, weight, count, unit")
    default_unit: str = Field(..., description="Default unit: ml, g, pcs")
    default_quantity: Decimal | None = Field(None, gt=0, description="Default quantity")
    min_stock_quantity: Decimal | None = Field(None, ge=0, description="Minimum stock threshold")
    reorder_quantity: Decimal | None = Field(None, gt=0, description="Reorder quantity")
    off_product_id: str | None = Field(None, description="Open Food Facts product ID")


class ProductMasterCreate(ProductMasterBase):
    """Schema for creating a new product."""

    pass


class ProductMasterUpdate(BaseModel):
    """Schema for updating a product."""

    canonical_name: str | None = None
    category: str | None = None
    storage_type: str | None = None
    default_shelf_life_days: int | None = Field(None, gt=0)
    opened_shelf_life_days: int | None = Field(None, gt=0)
    unit_type: str | None = None
    default_unit: str | None = None
    default_quantity: Decimal | None = Field(None, gt=0)
    min_stock_quantity: Decimal | None = Field(None, ge=0)
    reorder_quantity: Decimal | None = Field(None, gt=0)
    off_product_id: str | None = None


class ProductMasterResponse(ProductMasterBase):
    """Schema for product API responses."""

    id: UUID
    off_data: dict | None = Field(None, description="Cached Open Food Facts data")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
