from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field, WithJsonSchema, model_validator

from app.schemas.types import JsonDecimal, canonicalize_units


class ShoppingPriority(StrEnum):
    """How badly it is needed."""

    URGENT = "urgent"
    NORMAL = "normal"
    LOW = "low"


class ShoppingSource(StrEnum):
    """Why the line is on the list - who or what put it there."""

    MANUAL = "manual"
    AUTO_RESTOCK = "auto_restock"
    RECIPE = "recipe"


class ShoppingListItemBase(BaseModel):
    """Base shopping list item schema with common fields."""

    product_master_id: UUID | None = Field(
        None, description="Product master ID (null for free-text items)"
    )
    name: str = Field(..., description="Display name")
    quantity: JsonDecimal = Field(..., gt=0, description="Quantity to purchase")
    unit: str = Field(
        ..., description="Unit: dl, tsp, tbsp, g, pcs (others convert on write)"
    )
    priority: ShoppingPriority = Field(
        ShoppingPriority.NORMAL, description="How badly it is needed"
    )
    source: ShoppingSource = Field(
        ShoppingSource.MANUAL, description="Why the line is on the list"
    )


class ShoppingListItemCreate(ShoppingListItemBase):
    """Schema for creating a new shopping list item."""

    @model_validator(mode="after")
    def canonical_units(self) -> "ShoppingListItemCreate":
        canonicalize_units(self, "unit", ["quantity"])
        return self


class ShoppingListItemUpdate(BaseModel):
    """Schema for updating a shopping list item."""

    product_master_id: UUID | None = None
    name: str | None = None
    quantity: JsonDecimal | None = Field(None, gt=0)
    unit: str | None = None
    priority: ShoppingPriority | None = None
    is_purchased: bool | None = None

    @model_validator(mode="after")
    def canonical_units(self) -> "ShoppingListItemUpdate":
        canonicalize_units(self, "unit", ["quantity"])
        return self


class ShoppingListItemResponse(ShoppingListItemBase):
    """Schema for shopping list item API responses."""

    id: UUID
    is_purchased: bool
    added_at: datetime
    purchased_at: datetime | None = None

    model_config = {"from_attributes": True}


#: The sources `POST /api/shopping/generate` understands (``shopping_generate.SOURCES``).
#: ``recipe`` and ``meal_plan`` wait for AG5.
GENERATE_SOURCES: tuple[str, ...] = ("low_stock",)


def _sources_required(schema: dict[str, Any]) -> None:
    """Publish ``sources`` as required. The field defaults to None only so that a missing
    one reaches the service and is refused as 400 ``invalid`` rather than a 422."""
    required = schema.setdefault("required", [])
    if "sources" not in required:
        required.insert(0, "sources")


class ShoppingGenerateRequest(BaseModel):
    """What to build a shopping list from (AG6). Only ``low_stock`` exists for now.

    ``sources`` takes any JSON value here and is checked by the service: anything but a
    non-empty list of known source names (a bare string, an object, a list holding an
    object, an unknown name, an empty list, or no ``sources`` at all) is 400 ``invalid``,
    so an agent gets the stable error shape rather than a 422. The schema still documents
    it as a required list of names. ``dry_run`` is validated as usual.
    """

    sources: Annotated[
        Any,
        WithJsonSchema(
            {
                "type": "array",
                "items": {"type": "string", "enum": list(GENERATE_SOURCES)},
            }
        ),
    ] = Field(None, description="low_stock: every product below its min_stock_quantity")
    dry_run: bool = Field(False, description="Plan only; nothing is written")

    model_config = {"json_schema_extra": _sources_required}


class ShoppingGenerateLine(BaseModel):
    """One product the generator looked at, and what came of it.

    ``need``, ``on_hand`` and ``min_stock`` are in ``unit``, the product's own unit.
    ``item_id`` is the list item added, raised or left alone (none on a dry run's added
    lines). A skipped line says why in ``reason``, and there are two causes:

    - The stock could not be counted: some of it is in a unit that does not convert to
      the product's (``"stock in tsp cannot be counted against min_stock in dl"``). No
      ``need``, ``on_hand`` or ``item_id``: nothing is known to be short.
    - The need is known but the open list item for the product is in a unit that cannot
      hold it (``"the open list item is in g, which cannot hold a need in dl"``). Carries
      ``need`` and ``on_hand``, and ``item_id`` is that open item, left as it was; no
      second item is added beside it.
    """

    product_id: UUID
    name: str
    need: JsonDecimal | None = None
    unit: str
    on_hand: JsonDecimal | None = None
    min_stock: JsonDecimal
    item_id: UUID | None = None
    reason: str | None = None


class ShoppingGenerateResponse(BaseModel):
    """added: new list items. updated: open items raised to the need. unchanged: open
    items already big enough. skipped: products whose stock could not be counted, or
    whose open item's unit cannot hold the need (``ShoppingGenerateLine`` says which)."""

    added: list[ShoppingGenerateLine] = Field(default_factory=list)
    updated: list[ShoppingGenerateLine] = Field(default_factory=list)
    unchanged: list[ShoppingGenerateLine] = Field(default_factory=list)
    skipped: list[ShoppingGenerateLine] = Field(default_factory=list)
    dry_run: bool
