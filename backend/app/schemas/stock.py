"""Request and response shapes of the agent-facing stock and product routes (AG2)."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.inventory_item import InventoryItemResponse, StorageLocation
from app.schemas.types import JsonDecimal
from app.services.units import canonical_factor


class StockRow(BaseModel):
    """One product's stock in one unit: every item still in the kitchen, added up."""

    product_id: UUID
    product_name: str
    category: str
    category_icon: str | None = None
    unit: str = Field(..., description="dl, tsp, tbsp, g or pcs")
    total: JsonDecimal = Field(..., description="Sum of current_quantity, in unit")
    item_count: int
    earliest_expiry: date
    locations: dict[str, JsonDecimal] = Field(
        ..., description="Total per storage location, in unit"
    )
    expiring: bool = Field(
        ..., description="The earliest expiry is at most 3 days away, or already past"
    )


class StockAddResponse(BaseModel):
    item: InventoryItemResponse
    product_created: bool


class StockConsumeRequest(BaseModel):
    """Consume by product name (or id), first to expire first, across items."""

    product: str | None = Field(
        None, description="A product name: canonical or learned, matched exactly"
    )
    product_id: UUID | None = None
    amount: JsonDecimal = Field(..., gt=0)
    unit: str = Field(
        ..., description="dl, tsp, tbsp, g, pcs, or one converting to them"
    )
    location: StorageLocation | None = Field(
        None, description="Only items in this location"
    )
    dry_run: bool = Field(False, description="Plan only; nothing is written")
    allow_partial: bool = Field(
        False, description="Consume what there is rather than refuse short stock"
    )

    @field_validator("unit")
    @classmethod
    def known_unit(cls, unit: str) -> str:
        canonical_factor(unit)  # raises ValueError -> 422
        return unit

    @model_validator(mode="after")
    def exactly_one_product(self) -> "StockConsumeRequest":
        if self.product is not None and not self.product.strip():
            self.product = None
        if (self.product is None) == (self.product_id is None):
            raise ValueError("Give exactly one of product or product_id")
        return self


class RequestedAmount(BaseModel):
    amount: JsonDecimal
    unit: str


class ConsumedFromItem(BaseModel):
    item_id: UUID
    amount: JsonDecimal = Field(..., description="Taken from this item, in its unit")
    unit: str
    remaining: JsonDecimal
    status: str


class StockConsumeResponse(BaseModel):
    product_id: UUID
    product_name: str
    requested: RequestedAmount
    consumed: list[ConsumedFromItem]
    remaining_total: JsonDecimal = Field(
        ..., description="What is left of the items that could be consumed, in unit"
    )
    unit: str = Field(..., description="The canonical unit of the request")
    dry_run: bool


class ProductMatch(BaseModel):
    product_id: UUID
    name: str
    source: str = Field(..., description="canonical, cook or model")


class ProductCandidate(BaseModel):
    product_id: UUID
    name: str
    score: float = Field(
        ..., description="Trigram similarity of its closest name, 0 to 1"
    )
    source: str = Field(..., description="Whose name that closest one is")


class ResolveResponse(BaseModel):
    match: ProductMatch | None
    candidates: list[ProductCandidate]
    suggestion: str | None = Field(
        None, description="The normalised name to create when nothing matched"
    )


class TeachNameRequest(BaseModel):
    name: str = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def not_blank(cls, name: str) -> str:
        if not name.strip():
            raise ValueError("name must not be blank")
        return name
