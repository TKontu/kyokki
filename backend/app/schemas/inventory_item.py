from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.types import JsonDecimal, canonicalize_units


class InventoryStatus(StrEnum):
    """Where an item is in its life. The column is a plain string; this is the vocabulary.

    Until H24 this was a `Literal` on the PATCH schema and a free `str` on create, so
    `POST /inventory` stored any string at all while `PATCH` answered 422 for the same value.
    The legal *moves* between these live in `services/item_status.py`; this is only the set.
    """

    SEALED = "sealed"
    OPENED = "opened"
    PARTIAL = "partial"
    EMPTY = "empty"
    DISCARDED = "discarded"


class ExpirySource(StrEnum):
    """How the expiry date was arrived at, which is what decides who may overwrite it.

    `calculated` is the only one any automatic recompute touches: `manual` is the cook's own
    date (Q12), `frozen` is the freezer clock (DEC-10), and `scanned` came off a barcode.
    """

    SCANNED = "scanned"
    CALCULATED = "calculated"
    MANUAL = "manual"
    FROZEN = "frozen"


class StorageLocation(StrEnum):
    """Where in the kitchen it physically is."""

    MAIN_FRIDGE = "main_fridge"
    FREEZER = "freezer"
    PANTRY = "pantry"


class UndoStepResponse(BaseModel):
    """One change the next undo would reverse."""

    inventory_item_id: UUID
    product_name: str
    unit: str
    action: str = Field(..., description="A ConsumptionAction")
    quantity_consumed: JsonDecimal = Field(..., description="How much the change moved")


class UndoPreviewResponse(BaseModel):
    """What the header's Undo would reverse: the most recent action, one or many items."""

    batch_id: UUID = Field(
        ..., description="Send this back to undo exactly this action"
    )
    logged_at: datetime
    steps: list[UndoStepResponse]


class UndoRequest(BaseModel):
    batch_id: UUID = Field(..., description="The batch the preview showed")


class UndoResponse(BaseModel):
    undone: int = Field(..., description="How many items were put back")


class BulkItemsRequest(BaseModel):
    """The items to move, by id (H23 events in bulk)."""

    ids: list[UUID] = Field(..., min_length=1, description="Inventory items to act on")


class BulkItemsResponse(BaseModel):
    """Counters rather than rows, as receipt confirm and the catalog estimate answer.

    `refused` is not a failure: an item already in the bin cannot be thrown away twice, and a
    cook clearing a shelf should not have the whole action fail because one of them had gone
    already.
    """

    changed: int = Field(..., description="Items that actually moved")
    refused: int = Field(
        0, description="Items already in the state asked for, or frozen against it"
    )
    missing: int = Field(0, description="Ids that matched no item")


class InventoryItemBase(BaseModel):
    """Base inventory item schema with common fields."""

    product_master_id: UUID = Field(..., description="Product master ID")
    receipt_id: UUID | None = Field(None, description="Source receipt ID")
    initial_quantity: JsonDecimal = Field(..., gt=0, description="Initial quantity")
    current_quantity: JsonDecimal = Field(..., ge=0, description="Current quantity")
    unit: str = Field(
        ..., description="Unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    status: InventoryStatus = Field(
        InventoryStatus.SEALED, description="Where the item is in its life"
    )
    purchase_date: date | None = Field(None, description="Purchase date")
    expiry_date: date = Field(..., description="Expiry date")
    expiry_source: ExpirySource = Field(
        ExpirySource.CALCULATED, description="How the expiry date was arrived at"
    )
    opened_date: date | None = Field(None, description="Date when opened")
    batch_number: str | None = Field(
        None, description="Batch number from GS1 DataMatrix"
    )
    location: StorageLocation = Field(
        StorageLocation.MAIN_FRIDGE, description="Where in the kitchen it is"
    )
    notes: str | None = Field(None, description="User notes")


class InventoryItemCreate(InventoryItemBase):
    """Schema for creating a new inventory item."""

    @model_validator(mode="after")
    def canonical_units(self) -> "InventoryItemCreate":
        canonicalize_units(self, "unit", ["initial_quantity", "current_quantity"])
        return self

    @model_validator(mode="after")
    def coherent_amounts_and_dates(self) -> "InventoryItemCreate":
        """Refuse a row that could never have come about (H23).

        Both of these were accepted until now, and each one makes the quantity bar or the
        expiry badge say something impossible for the life of the row. They run after
        `canonical_units`, so the comparison is between amounts in the same unit.
        """
        if self.current_quantity > self.initial_quantity:
            raise ValueError(
                f"current_quantity ({self.current_quantity}) cannot exceed "
                f"initial_quantity ({self.initial_quantity})"
            )
        if self.purchase_date is not None and self.expiry_date < self.purchase_date:
            raise ValueError(
                f"expiry_date ({self.expiry_date}) cannot be before "
                f"purchase_date ({self.purchase_date})"
            )
        return self


class QuickAddRequest(BaseModel):
    """Add stock by hand: an existing product, or a generic product found or created by name.

    A new product needs ``category``; its shelf life and storage come from the category
    (the same rules as receipt confirm). Expiry and location default from the product.
    """

    product_id: UUID | None = Field(None, description="Existing product")
    name: str | None = Field(
        None, description="Generic product name, reused case-insensitively or created"
    )
    category: str | None = Field(None, description="Category id for a new product")
    quantity: JsonDecimal = Field(..., gt=0, description="Amount in unit")
    unit: str | None = Field(
        None,
        description=(
            "Unit: dl, tsp, tbsp, g, pcs (others convert on write). Omit it and the "
            "resolved product's own unit is used - a typed name may resolve to a product "
            "the client has never seen"
        ),
    )
    location: StorageLocation | None = Field(
        None, description="Default follows the product's storage type"
    )
    purchase_date: date | None = Field(None, description="Default today")
    expiry_date: date | None = Field(
        None, description="Override; default purchase date + shelf life"
    )

    @model_validator(mode="after")
    def identifies_a_product(self) -> "QuickAddRequest":
        if self.name is not None and not self.name.strip():
            self.name = None
        if self.product_id is None and self.name is None:
            raise ValueError("Give a product_id or name")
        return self

    @model_validator(mode="after")
    def canonical_units(self) -> "QuickAddRequest":
        canonicalize_units(self, "unit", ["quantity"])
        return self


class InventoryItemUpdate(BaseModel):
    """Schema for updating an inventory item."""

    current_quantity: JsonDecimal | None = Field(
        None, ge=0, description="Correction: 0 empties; above the full amount raises it"
    )
    status: InventoryStatus | None = None
    expiry_date: date | None = Field(
        None, description="Sets expiry_source to manual unless expiry_source is given"
    )
    expiry_source: ExpirySource | None = None
    opened_date: date | None = None
    location: StorageLocation | None = None
    notes: str | None = None


class InventoryItemResponse(InventoryItemBase):
    """Schema for inventory item API responses."""

    id: UUID
    product_name: str = Field(..., description="Product canonical name")
    # The two numbers the iPad needs to predict what a consume does to the expiry (Q5, H25):
    # opening a pack shortens the clock, and loose produce is not a pack at all.
    opened_shelf_life_days: int | None = Field(
        None, description="How long this keeps once opened; null if it does not apply"
    )
    avg_piece_grams: JsonDecimal | None = Field(
        None, description="Roughly what one piece weighs, when sold loose and counted"
    )
    category: str = Field(..., description="Category ID, e.g. dairy")
    category_name: str = Field(..., description="Category display name")
    category_icon: str | None = Field(None, description="Category emoji icon")
    created_at: datetime
    consumed_at: datetime | None = None

    model_config = {"from_attributes": True}
