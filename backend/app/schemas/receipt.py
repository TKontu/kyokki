from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.services.storage import location_for_storage, storage_type_for_category
from app.services.units import receipt_line_quantity


class ReceiptStatus(StrEnum):
    """Receipt lifecycle. The column is a plain string; this is the single vocabulary."""

    UPLOADED = "uploaded"  # Rows from before MVP-R3; uploads are queued now
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFIRMED = "confirmed"


class ExtractedItem(BaseModel):
    """One receipt line as the review screen and confirm step see it."""

    index: int = Field(
        ..., description="Position on the receipt; items are addressed by it"
    )
    name: str = Field(..., description="Product name as printed")
    generic_name: str | None = Field(
        None, description="Brand-free generic name suggested for a new product"
    )
    quantity: float = Field(..., description="Amount in `unit`")
    unit: Literal["dl", "tsp", "tbsp", "g", "pcs"] = Field(
        ..., description="Canonical unit"
    )
    product_id: UUID | None = Field(None, description="Matched product")
    product_name: str | None = Field(
        None, description="Matched product's canonical name"
    )
    match_score: float | None = Field(None, description="0-100")
    match_confidence: Literal["exact", "high", "medium", "low"] | None = None
    match_source: Literal["alias", "exact", "fuzzy", "fuzzy_alias"] | None = None
    suggested_category: str | None = Field(
        None, description="Category id read from the line"
    )
    storage_type: Literal["refrigerator", "freezer", "pantry"] = Field(
        ..., description="Matched product's storage, else derived from the category"
    )
    location: Literal["main_fridge", "freezer", "pantry"] = Field(
        ..., description="Default inventory location for this item"
    )


def items_from_structured(structured: dict[str, Any] | None) -> list[ExtractedItem]:
    """Build typed items from ``receipt.ocr_structured``.

    Tolerates shapes written before MVP-R1b (no ``lines``, missing match fields): those give
    an empty list or default values instead of failing the response.
    """
    if not isinstance(structured, dict):
        return []
    lines = structured.get("lines")
    if not isinstance(lines, list):
        return []

    items: list[ExtractedItem] = []
    for index, line in enumerate(lines):
        if not isinstance(line, dict) or not line.get("name"):
            continue
        quantity, unit = receipt_line_quantity(
            line.get("quantity"), line.get("weight_kg")
        )
        category = line.get("category")
        storage = line.get("product_storage_type") or storage_type_for_category(
            category
        )
        if storage not in ("refrigerator", "freezer", "pantry"):
            storage = storage_type_for_category(category)
        items.append(
            ExtractedItem(
                index=index,
                name=line["name"],
                generic_name=line.get("generic_name"),
                quantity=quantity,
                unit=unit,
                product_id=line.get("product_id"),
                product_name=line.get("product_name"),
                match_score=line.get("match_score"),
                match_confidence=line.get("match_confidence"),
                match_source=line.get("match_source"),
                suggested_category=category,
                storage_type=storage,
                location=location_for_storage(storage),
            )
        )
    return items


class ReceiptBase(BaseModel):
    """Base receipt schema with common fields."""

    store_chain: str | None = Field(
        None, description="Chain key (e.g. s-group) or manual value"
    )
    purchase_date: date | None = Field(None, description="Purchase date")
    image_path: str = Field(..., description="Path to receipt image")
    batch_id: UUID | None = Field(
        None, description="Batch ID for multi-receipt processing"
    )


class ReceiptCreate(ReceiptBase):
    """Schema for creating a new receipt."""

    pass


class ReceiptUpdate(BaseModel):
    """Schema for updating a receipt."""

    store_chain: str | None = None
    purchase_date: date | None = None
    processing_status: ReceiptStatus | None = None


class ReceiptResponse(ReceiptBase):
    """Schema for receipt API responses."""

    id: UUID
    ocr_raw_text: str | None = Field(None, description="Raw OCR or PDF text")
    content_sha256: str | None = Field(None, description="SHA-256 of the uploaded file")
    ocr_structured: dict[str, Any] | None = Field(
        None, description="Stored extraction (debugging)"
    )
    processing_status: ReceiptStatus = Field(..., description="Processing status")
    error: str | None = Field(None, description="Last processing failure, if any")
    queued_at: datetime | None = Field(None, description="When it entered the queue")
    processing_started_at: datetime | None = Field(
        None, description="When the worker started reading it"
    )
    items_extracted: int = Field(0, description="Number of items extracted")
    items_matched: int = Field(0, description="Number of items matched to products")
    extraction_method: Literal["text", "vision", "heuristic"] | None = Field(
        None,
        description="text or vision: the model; heuristic: the fallback line parser",
    )
    fallback_reason: str | None = Field(
        None, description="Why the heuristic parser was used instead of the model"
    )
    items: list[ExtractedItem] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def derive_items(self) -> "ReceiptResponse":
        self.items = items_from_structured(self.ocr_structured)
        method = (self.ocr_structured or {}).get("method")
        self.extraction_method = (
            method if method in ("text", "vision", "heuristic") else None
        )
        reason = (self.ocr_structured or {}).get("fallback_reason")
        self.fallback_reason = reason if isinstance(reason, str) else None
        return self


class ConfirmedItemCreate(BaseModel):
    """One reviewed receipt item to add to inventory.

    Give ``product_id`` for an existing product. Otherwise a generic product is reused by name
    or created: ``name`` and ``category`` default to the receipt line's generic name and
    category. ``index`` names the receipt line, so its printed name is learned as an alias.
    """

    index: int | None = Field(
        None, ge=0, description="Receipt line; its printed name is learned as an alias"
    )
    product_id: UUID | None = Field(None, description="Existing product")
    name: str | None = Field(
        None, description="Generic product name when product_id is not given"
    )
    category: str | None = Field(None, description="Category id for a new product")
    quantity: float = Field(..., gt=0, description="Quantity to add")
    unit: str = Field(
        ..., description="Unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    purchase_date: date = Field(..., description="Purchase date for expiry calculation")
    expiry_date: date | None = Field(
        None, description="Override; default is purchase date + shelf life"
    )
    location: Literal["main_fridge", "freezer", "pantry"] | None = Field(
        None, description="Override; default follows the product's storage type"
    )

    @model_validator(mode="after")
    def identifies_a_product(self) -> "ConfirmedItemCreate":
        if self.name is not None and not self.name.strip():
            self.name = None
        if self.product_id is None and self.name is None and self.index is None:
            raise ValueError("Each item needs a product_id, name or index")
        return self

    @model_validator(mode="after")
    def canonical_units(self) -> "ConfirmedItemCreate":
        from app.services.units import canonical_factor, to_canonical_decimal

        _, canonical = canonical_factor(self.unit)
        converted = to_canonical_decimal(Decimal(str(self.quantity)), self.unit)
        self.quantity = float(converted) if converted is not None else self.quantity
        self.unit = canonical
        return self


class ReceiptConfirmRequest(BaseModel):
    """Schema for receipt confirmation request."""

    items: list[ConfirmedItemCreate] = Field(
        ..., description="Confirmed items to add to inventory"
    )


class ReceiptConfirmResponse(BaseModel):
    """Schema for receipt confirmation response."""

    success: bool = Field(..., description="Whether confirmation succeeded")
    items_created: int = Field(0, description="Number of inventory items created")
    products_created: int = Field(0, description="New generic products created")
    aliases_learned: int = Field(0, description="Printed names learned or reinforced")
    error: str | None = Field(None, description="Error message if confirmation failed")
