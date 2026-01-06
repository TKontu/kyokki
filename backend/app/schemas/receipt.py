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


class ReceiptProcessingResponse(BaseModel):
    """Schema for receipt processing result."""

    success: bool = Field(..., description="Whether processing succeeded")
    items_extracted: int = Field(0, description="Number of products extracted")
    items_matched: int = Field(0, description="Number of products matched")
    error: str | None = Field(None, description="Error message if processing failed")


class ConfirmedItemCreate(BaseModel):
    """Schema for a confirmed receipt item to add to inventory."""

    product_id: UUID = Field(..., description="Product master ID")
    quantity: float = Field(..., gt=0, description="Quantity to add")
    unit: str = Field(..., description="Unit (pcs, kg, l, etc.)")
    purchase_date: date = Field(..., description="Purchase date for expiry calculation")


class ReceiptConfirmRequest(BaseModel):
    """Schema for receipt confirmation request."""

    items: list[ConfirmedItemCreate] = Field(..., description="Confirmed items to add to inventory")


class ReceiptConfirmResponse(BaseModel):
    """Schema for receipt confirmation response."""

    success: bool = Field(..., description="Whether confirmation succeeded")
    items_created: int = Field(0, description="Number of inventory items created")
    error: str | None = Field(None, description="Error message if confirmation failed")
