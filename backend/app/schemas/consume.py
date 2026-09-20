"""Schema for consume operation."""

from decimal import Decimal

from pydantic import BaseModel, Field


class ConsumeRequest(BaseModel):
    """How much of an item was eaten or used.

    `unit` is optional and exists for callers that are not the iPad (H23). The app consumes in
    whatever unit the item is stored in and can leave it out; an agent asking to consume "200 g"
    of something the kitchen counts in pieces is a mistake worth catching at the door rather
    than silently subtracting 200 from a count of 12.
    """

    quantity: Decimal = Field(..., gt=0, description="Quantity to consume")
    unit: str | None = Field(
        None,
        description=(
            "Unit of `quantity`. Omit to use the item's own unit. Converted when it is the "
            "same kind of measure, refused when it is not."
        ),
    )
