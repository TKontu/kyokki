from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StoreProductAliasBase(BaseModel):
    """Base store product alias schema with common fields."""

    product_master_id: UUID = Field(..., description="Product master ID")
    store_chain: str = Field(..., description="Store chain name")
    receipt_name: str = Field(..., description="Product name as it appears on receipt")
    barcode: str | None = Field(None, description="Product barcode (EAN-13, UPC, GTIN)")
    confidence_score: float = Field(0.0, ge=0.0, le=1.0, description="Matching confidence score")
    manually_verified: bool = Field(False, description="Whether mapping was manually verified")


class StoreProductAliasCreate(StoreProductAliasBase):
    """Schema for creating a new store product alias."""

    pass


class StoreProductAliasUpdate(BaseModel):
    """Schema for updating a store product alias."""

    product_master_id: UUID | None = None
    store_chain: str | None = None
    receipt_name: str | None = None
    barcode: str | None = None
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)
    manually_verified: bool | None = None


class StoreProductAliasResponse(StoreProductAliasBase):
    """Schema for store product alias API responses."""

    id: UUID
    occurrence_count: int = Field(..., description="Number of times seen")
    last_seen: datetime

    model_config = {"from_attributes": True}
