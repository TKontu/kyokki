from datetime import date, datetime
from typing import Literal
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
        "calculated", description="Expiry source: scanned, calculated, manual, frozen"
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
    unit: str = Field(
        ..., description="Unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    location: Literal["main_fridge", "freezer", "pantry"] | None = Field(
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
    status: Literal["sealed", "opened", "partial", "empty", "discarded"] | None = None
    expiry_date: date | None = Field(
        None, description="Sets expiry_source to manual unless expiry_source is given"
    )
    expiry_source: Literal["scanned", "calculated", "manual", "frozen"] | None = None
    opened_date: date | None = None
    location: Literal["main_fridge", "freezer", "pantry"] | None = None
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
