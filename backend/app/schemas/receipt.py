from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.services.storage import location_for_storage, storage_type_for_category
from app.services.units import (
    grams_to_pieces,
    pieces_to_grams,
    receipt_line_quantity,
)


class ReceiptStatus(StrEnum):
    """Receipt lifecycle. The column is a plain string; this is the single vocabulary."""

    UPLOADED = "uploaded"  # Rows from before MVP-R3; uploads are queued now
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFIRMED = "confirmed"


# How a line came to point at a product (docs/PRODUCT_RESOLUTION_SPEC.md §3.1). Every
# value but `selected` is an exact key; `selected` is a proposal the cook can change.
MatchSource = Literal["alias", "name", "selected", "none"]

# Values written before H12, mapped forward by `items_from_structured`. `fuzzy` and
# `fuzzy_alias` were similarity guesses, which is exactly what `selected` now means to
# the review row: proposed, not keyed.
LEGACY_MATCH_SOURCES: dict[str, MatchSource] = {
    "alias": "alias",
    "exact": "name",
    "fuzzy": "selected",
    "fuzzy_alias": "selected",
}


def normalise_match_source(raw: object) -> MatchSource | None:
    """Accept both vocabularies, so receipts already in the database still render."""
    if raw is None:
        return None
    value = str(raw)
    if value in ("alias", "name", "selected", "none"):
        return value  # type: ignore[return-value]
    return LEGACY_MATCH_SOURCES.get(value)


class ExtractedItem(BaseModel):
    """One receipt line as the review screen and confirm step see it."""

    index: int = Field(
        ...,
        description=(
            "Position among the readable lines. Kept for one release; address lines by "
            "`line_id` instead, which does not shift when a line is skipped"
        ),
    )
    line_id: UUID | None = Field(
        None,
        description=(
            "Stable identity for this receipt line, kept across re-reads. Absent on "
            "receipts read before H12"
        ),
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
    match_source: MatchSource | None = Field(
        None,
        description=(
            "How this product was arrived at: `alias` (a learned printed name), `name` "
            "(a known catalog name), `selected` (proposed, not from a key), `none`"
        ),
    )
    verified: bool = Field(
        False,
        description=(
            "The mapping came from a key the cook has confirmed, rather than a proposal"
        ),
    )
    suggested_category: str | None = Field(
        None, description="Category id read from the line"
    )
    piece_grams: float | None = Field(
        None,
        description="Roughly what one piece weighs, when the line was sold by weight (Q2)",
    )
    shelf_life_days: int | None = Field(
        None, description="Typical days this keeps; overrides the category default (Q6)"
    )
    opened_shelf_life_days: int | None = Field(
        None, description="Typical days this keeps once opened (Q5)"
    )
    non_food: bool = Field(
        False, description="Household or cleaning; not offered as food (Q1)"
    )
    pack_grams: float | None = Field(
        None,
        description="Roughly what one pack weighs, when the line was sold by the pack (Q8)",
    )
    printed_quantity: float | None = Field(
        None, description="What the receipt said, when the unit was converted"
    )
    printed_unit: str | None = Field(
        None, description="Unit the receipt used, when the unit was converted"
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
        resolution = line.get("resolution")
        resolution = resolution if isinstance(resolution, dict) else {}
        quantity, unit = receipt_line_quantity(
            line.get("quantity"), line.get("weight_kg")
        )
        # A shop sells apples by the kilo; the cook counts them. Show pieces, but keep what
        # the receipt printed so the conversion is visible and can be overridden (Q2).
        piece_grams = line.get("piece_grams")
        pack_grams = line.get("pack_grams")
        printed_quantity: float | None = None
        printed_unit: str | None = None
        if unit == "g":
            pieces = grams_to_pieces(quantity, piece_grams)
            if pieces is not None:
                printed_quantity, printed_unit = quantity, unit
                quantity, unit = float(pieces), "pcs"
        elif unit == "pcs" and not piece_grams:
            # The mirror (Q8): the shop counted packs, the cook measures. A piece
            # weight wins, so this only runs when the line has none.
            grams = pieces_to_grams(quantity, pack_grams)
            if grams is not None:
                printed_quantity, printed_unit = quantity, unit
                quantity, unit = grams, "g"
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
                line_id=line.get("line_id"),
                match_source=normalise_match_source(
                    resolution.get("source", line.get("match_source"))
                ),
                verified=bool(resolution.get("verified", False)),
                suggested_category=category,
                piece_grams=piece_grams,
                pack_grams=pack_grams,
                shelf_life_days=line.get("shelf_life_days"),
                opened_shelf_life_days=line.get("opened_shelf_life_days"),
                non_food=bool(line.get("non_food")),
                printed_quantity=printed_quantity,
                printed_unit=printed_unit,
                storage_type=storage,
                location=location_for_storage(storage),
            )
        )
    return items


def method_from_structured(
    structured: dict[str, Any] | None,
) -> tuple[Literal["text", "vision", "heuristic"] | None, str | None]:
    """Read how a receipt was extracted out of ``receipt.ocr_structured``.

    Neither value is a column: the pipeline stores them inside the structured blob.
    """
    method = (structured or {}).get("method")
    reason = (structured or {}).get("fallback_reason")
    return (
        method if method in ("text", "vision", "heuristic") else None,
        reason if isinstance(reason, str) else None,
    )


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
        self.extraction_method, self.fallback_reason = method_from_structured(
            self.ocr_structured
        )
        return self


class ReceiptSummary(BaseModel):
    """One receipt as the receipts list shows it (MVP-R8).

    The iPad polls the list, so it deliberately leaves out ``ocr_raw_text``,
    ``ocr_structured`` and the derived ``items``: on a real receipt those are tens of
    kilobytes each, and the list only renders counts and a status.
    """

    id: UUID
    store_chain: str | None = None
    purchase_date: date | None = None
    processing_status: ReceiptStatus
    error: str | None = None
    queued_at: datetime | None = None
    processing_started_at: datetime | None = None
    items_extracted: int = 0
    items_matched: int = 0
    extraction_method: Literal["text", "vision", "heuristic"] | None = None
    fallback_reason: str | None = None
    created_at: datetime

    # Read to derive the two fields above; never serialised
    ocr_structured: dict[str, Any] | None = Field(None, exclude=True)

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def derive_method(self) -> "ReceiptSummary":
        self.extraction_method, self.fallback_reason = method_from_structured(
            self.ocr_structured
        )
        return self


class ConfirmedItemCreate(BaseModel):
    """One reviewed receipt item to add to inventory.

    Give ``product_id`` for an existing product. Otherwise a generic product is reused by name
    or created: ``name`` and ``category`` default to the receipt line's generic name and
    category. ``index`` names the receipt line, so its printed name is learned as an alias.
    """

    index: int | None = Field(
        None,
        ge=0,
        description=(
            "Receipt line by position; its printed name is learned as an alias. "
            "Prefer `line_id`, which does not shift when a line is unreadable"
        ),
    )
    line_id: UUID | None = Field(
        None,
        description="Receipt line by identity; wins over `index` when both are given",
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
        if (
            self.product_id is None
            and self.name is None
            and self.index is None
            and self.line_id is None
        ):
            raise ValueError("Each item needs a product_id, name, index or line_id")
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
    non_food_indexes: list[int] = Field(
        default_factory=list,
        description="Lines the cook says are not food; their names are remembered (Q1)",
    )


class ReceiptConfirmResponse(BaseModel):
    """Schema for receipt confirmation response."""

    success: bool = Field(..., description="Whether confirmation succeeded")
    items_created: int = Field(0, description="Number of inventory items created")
    products_created: int = Field(0, description="New generic products created")
    aliases_learned: int = Field(0, description="Printed names learned or reinforced")
    error: str | None = Field(None, description="Error message if confirmation failed")
