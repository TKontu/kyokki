"""Request and response bodies of the split API (CL8 L2).

The contract is shared with the frontend this round (`docs/PRODUCT_IDENTITY_SPEC.md`,
"Undoing a wrong join: split"): `GET /products/{id}/sources`, `POST /products/{id}/split`
and `POST /products/reassignments/{id}/undo`.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.product_master import ProductMasterResponse


class ProductSource(BaseModel):
    """One group of a product's items, by where they came from."""

    key: str = Field(..., description="Stable opaque id of the group")
    label: str = Field(
        ..., description="Printed receipt text, or an empty string for hand-added items"
    )
    store_chain: str | None = Field(None, description="Null when not from a receipt")
    kind: Literal["receipt", "manual"]
    item_ids: list[UUID] = Field(
        ..., description="Active items (not used up or thrown away) in the group"
    )
    active_count: int
    total_count: int = Field(..., description="Including used up and thrown away")
    first_seen: date | None = Field(None, description="Earliest purchase date")
    last_seen: date | None = Field(None, description="Latest purchase date")


class ProductSourcesResponse(BaseModel):
    product_id: UUID
    sources: list[ProductSource]


class ExistingTarget(BaseModel):
    product_id: UUID


class NewTargetProduct(BaseModel):
    # No length rules here: an empty name or unknown category is the contract's 400
    # `invalid`, not a 422.
    name: str
    category: str


class NewTarget(BaseModel):
    new: NewTargetProduct


class SplitRequest(BaseModel):
    item_ids: list[UUID] = Field(
        ..., description="At least one; all currently on this product"
    )
    target: ExistingTarget | NewTarget
    move_keys: bool = Field(
        True,
        description=(
            "Re-point the moved lines' printed-name aliases to the target as the cook's "
            "word, and forget the names the model taught from them"
        ),
    )


class MovedKey(BaseModel):
    kind: Literal["alias", "name"]
    value: str
    store_chain: str | None = None


class SourceShelfLife(BaseModel):
    days: int
    source: Literal["cook", "model", "category"]
    observations_left: int


class SplitResponse(BaseModel):
    reassignment_id: UUID
    source_product: ProductMasterResponse
    target_product: ProductMasterResponse
    target_created: bool
    moved_item_ids: list[UUID]
    moved_keys: list[MovedKey]
    source_shelf_life: SourceShelfLife


class UndoSplitResponse(BaseModel):
    reassignment_id: UUID
    restored_item_ids: list[UUID]
