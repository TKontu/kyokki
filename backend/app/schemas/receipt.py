from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReceiptBase(BaseModel):
    """Base receipt schema with common fields."""

    store_chain: str | None = Field(None, description="Detected or manual store chain")
    purchase_date: date | None = Field(None, description="Purchase date")
    image_path: str = Field(..., description="Path to receipt image")
    batch_id: UUID | None = Field(None, description="Batch ID for multi-receipt processing")


class ReceiptCreate(ReceiptBase):
    """Schema for creating a new receipt."""

    pass


class ReceiptUpdate(BaseModel):
    """Schema for updating a receipt."""

    store_chain: str | None = None
    purchase_date: date | None = None
    processing_status: str | None = Field(None, description="queued, processing, completed, failed")


class ReceiptResponse(ReceiptBase):
    """Schema for receipt API responses."""

    id: UUID
    ocr_raw_text: str | None = Field(None, description="Raw OCR output")
    ocr_structured: dict | None = Field(None, description="Parsed items and metadata")
    processing_status: str = Field(..., description="Processing status")
    items_extracted: int = Field(0, description="Number of items extracted")
    items_matched: int = Field(0, description="Number of items matched to products")
    created_at: datetime

    model_config = {"from_attributes": True}
