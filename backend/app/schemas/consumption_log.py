from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.types import JsonDecimal


class ConsumptionAction(StrEnum):
    """What happened to an item's quantity, one row per event (H46).

    The distinction this whole column exists for is `discard` against the two `use_` values:
    thrown away is waste, eaten is not, and reducing waste is the point of the app. The other
    two make the history replayable: `restore` brings a thrown-away item back, `correct` is
    the cook fixing a number by hand. Neither is consumption, and a waste total must not count
    them.

    Follows `services.item_status.ItemEvent`, with consume split in two so "finished it" can
    be told from "had some".
    """

    USE_PARTIAL = "use_partial"
    USE_FULL = "use_full"
    DISCARD = "discard"
    RESTORE = "restore"
    CORRECT = "correct"


class ActionSummary(BaseModel):
    """What one kind of event added up to in a window."""

    events: int = Field(..., description="How many times it happened")
    totals: dict[str, JsonDecimal] = Field(
        ..., description="How much, per unit - grams and pieces do not add up"
    )


class ConsumptionLogResponse(BaseModel):
    """One event in an item's history, readable on its own.

    `quantity_consumed` is how much the event moved, always positive - the name predates
    `restore` and `correct`, which move food the other way; `quantity_after` is what was left
    once it had. A correction can go either way, and the pair is what says which.
    """

    id: UUID
    inventory_item_id: UUID | None = Field(
        None, description="None once the item has been deleted; the record stays"
    )
    item_status: str | None = Field(
        None, description="Where the item stands now, or None if it is gone"
    )
    product_master_id: UUID
    product_name: str = Field(..., description="The product's name, for display")
    unit: str = Field(..., description="The unit both quantities are in")
    action: ConsumptionAction = Field(..., description="What happened")
    quantity_consumed: JsonDecimal = Field(
        ..., gt=0, description="How much the event moved"
    )
    quantity_after: JsonDecimal = Field(..., ge=0, description="What was left after it")
    logged_at: datetime

    model_config = {"from_attributes": True}
