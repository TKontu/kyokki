"""Receipt extraction result models.

The LLM returns a compact JSON contract (see ``app.services.llm_extractor``); it is mapped to
these models before anything else in the pipeline sees it.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

ExtractionMethod = Literal["text", "vision"]


class ExtractedLine(BaseModel):
    """One purchased product line as read from the receipt."""

    name: str = Field(
        ..., min_length=1, description="Product name as printed, without price"
    )
    quantity: float = Field(default=1.0, ge=0, description="Count from an 'n KPL' line")
    weight_kg: float | None = Field(
        default=None, ge=0, description="Weight from an 'x,xxx KG' line"
    )
    category: str | None = Field(default=None, description="Suggested category id")


class ReceiptExtraction(BaseModel):
    """Structured result of reading one receipt."""

    method: ExtractionMethod = Field(
        ...,
        description="text: OCR or PDF text was read; vision: the image was read directly",
    )
    store_chain: str | None = Field(
        default=None, description="Store or chain from the header"
    )
    purchase_date: date | None = Field(
        default=None, description="Purchase date if printed"
    )
    lines: list[ExtractedLine] = Field(default_factory=list)
