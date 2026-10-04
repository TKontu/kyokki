"""Response shapes for the run-out forecast (Phase 3 "Consumption Learning", frontier
item 8, `docs/TODO.md`): `GET /api/stock/runout` (the agent API) and `GET /api/ha/runout`
(Home Assistant's compact list). See `services.runout` for the method.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.types import JsonDecimal

RunoutStatus = Literal["forecast", "insufficient_history", "out"]


class RunoutProduct(BaseModel):
    """One product's forecast, in its own unit (`ProductMaster.default_unit`).

    `daily_rate`, `runs_out_on` and `days_left` are null together exactly when `status`
    is `insufficient_history`; `runs_out_on` is also null - with `days_left` at 0 - when
    `status` is `out`, and null with `days_left` also null when the rate itself is 0 (a
    `forecast` with no end in sight at the current pace).
    """

    product_id: UUID
    name: str
    unit: str = Field(..., description="dl, tsp, tbsp, g or pcs")
    active_stock: JsonDecimal = Field(..., description="On hand now, in unit")
    daily_rate: JsonDecimal | None = Field(
        None,
        description=(
            "Consumed per day in stock over the lookback window (days with none in "
            "stock do not count); null without enough history"
        ),
    )
    runs_out_on: date | None = Field(
        None,
        description="today + active_stock / daily_rate; null at a rate of 0 or no stock",
    )
    days_left: int | None = Field(
        None, description="0 when already out; null without enough history"
    )
    expires_first: bool = Field(
        ..., description="The earliest active item expires before runs_out_on"
    )
    status: RunoutStatus = Field(
        ..., description="forecast, insufficient_history or out"
    )

    model_config = {"from_attributes": True}


class HaRunoutItem(BaseModel):
    """`GET /api/ha/runout`: HA's compact shape, one line per product."""

    id: UUID
    name: str
    unit: str
    days_left: int | None
    runs_out_on: date | None
    status: RunoutStatus


class HaRunoutResponse(BaseModel):
    """`GET /api/ha/runout`: read-only, never writes anything, as `low-stock` is."""

    items: list[HaRunoutItem]
    count: int
    out_count: int = Field(
        ...,
        description=(
            "Products already at zero stock that would be listed with "
            "include_out=true, whether or not they are in items"
        ),
    )
