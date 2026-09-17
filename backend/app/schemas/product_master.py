from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.types import JsonDecimal, canonicalize_units
from app.services.units import unit_type_for


class ProductMasterBase(BaseModel):
    """Base product master schema with common fields."""

    canonical_name: str = Field(..., description="Canonical product name")
    category: str = Field(..., description="Product category ID")
    storage_type: str = Field(
        ..., description="Storage type: refrigerator, freezer, pantry"
    )
    default_shelf_life_days: int = Field(
        ..., gt=0, description="Default shelf life (unopened)"
    )
    avg_piece_grams: JsonDecimal | None = Field(
        None,
        gt=0,
        description="Roughly what one piece weighs, so weighed produce can be counted (Q2)",
    )
    opened_shelf_life_days: int | None = Field(
        None, gt=0, description="Shelf life after opening"
    )
    unit_type: str = Field(
        ...,
        description="Unit type: volume, weight, count (derived from default_unit on write)",
    )
    default_unit: str = Field(
        ..., description="Default unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    default_quantity: JsonDecimal | None = Field(
        None, gt=0, description="Default quantity"
    )
    min_stock_quantity: JsonDecimal | None = Field(
        None, ge=0, description="Minimum stock threshold"
    )
    reorder_quantity: JsonDecimal | None = Field(
        None, gt=0, description="Reorder quantity"
    )
    off_product_id: str | None = Field(None, description="Open Food Facts product ID")


class ProductMasterCreate(ProductMasterBase):
    """Schema for creating a new product."""

    @model_validator(mode="after")
    def canonical_units(self) -> "ProductMasterCreate":
        unit = canonicalize_units(
            self,
            "default_unit",
            ["default_quantity", "min_stock_quantity", "reorder_quantity"],
        )
        if unit:
            self.unit_type = unit_type_for(unit)
        return self


class ProductMasterUpdate(BaseModel):
    """Schema for updating a product."""

    canonical_name: str | None = None
    category: str | None = None
    storage_type: str | None = None
    default_shelf_life_days: int | None = Field(None, gt=0)
    avg_piece_grams: JsonDecimal | None = Field(None, gt=0)
    opened_shelf_life_days: int | None = Field(None, gt=0)
    unit_type: str | None = None
    default_unit: str | None = None
    default_quantity: JsonDecimal | None = Field(None, gt=0)
    min_stock_quantity: JsonDecimal | None = Field(None, ge=0)
    reorder_quantity: JsonDecimal | None = Field(None, gt=0)
    off_product_id: str | None = None

    @model_validator(mode="after")
    def canonical_units(self) -> "ProductMasterUpdate":
        unit = canonicalize_units(
            self,
            "default_unit",
            ["default_quantity", "min_stock_quantity", "reorder_quantity"],
        )
        if unit:
            self.unit_type = unit_type_for(unit)
        return self


class ProductMasterResponse(ProductMasterBase):
    """Schema for product API responses."""

    id: UUID
    off_data: dict | None = Field(None, description="Cached Open Food Facts data")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
