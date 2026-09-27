"""Receipt extraction result models.

The LLM returns a compact JSON contract (see ``app.services.llm_extractor``); it is mapped to
these models before anything else in the pipeline sees it.
"""

from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, Field

ExtractionMethod = Literal["text", "vision", "heuristic"]

# How a line the first model read left out was put back (Q27): read again by the model in
# one targeted call, or listed as the printed line itself for the cook to decide.
RecoveredBy = Literal["model_retry", "raw_line"]

# What a numbered receipt line that is not part of a product is (Q27)
OtherLineKind = Literal[
    "header",
    "total",
    "subtotal",
    "tax",
    "payment",
    "discount",
    "deposit",
    "fee",
    "other",
]
OTHER_LINE_KINDS: tuple[str, ...] = get_args(OtherLineKind)


class ExtractedLine(BaseModel):
    """One purchased product line as read from the receipt."""

    name: str = Field(
        ..., min_length=1, description="Product name as printed, without price"
    )
    generic_name: str | None = Field(
        default=None,
        description="Brand-free generic English name, e.g. 'Ground beef' (MVP-R2)",
    )
    quantity: float = Field(default=1.0, ge=0, description="Count from an 'n KPL' line")
    weight_kg: float | None = Field(
        default=None, ge=0, description="Weight from an 'x,xxx KG' line"
    )
    category: str | None = Field(default=None, description="Suggested category id")
    piece_grams: float | None = Field(
        default=None,
        description="Roughly what one of them weighs, for produce sold by weight (Q2)",
    )
    shelf_life_days: int | None = Field(
        default=None,
        description="Typical days this keeps unopened; overrides the category default (Q6)",
    )
    opened_shelf_life_days: int | None = Field(
        default=None,
        description="Typical days this keeps once opened, for things that are opened (Q5)",
    )
    non_food: bool = Field(
        default=False,
        description="Household or cleaning, not something that belongs in the fridge (Q1)",
    )
    source_lines: list[int] = Field(
        default_factory=list,
        description="Numbers of the receipt lines this product was read from (Q27)",
    )
    price: float | None = Field(
        default=None,
        description="The line total as printed, never the unit price (Q27)",
    )
    recovered: RecoveredBy | None = Field(
        default=None,
        description="Set when the first model read missed this line and it was put back (Q27)",
    )


class OtherLine(BaseModel):
    """A numbered receipt line the model says is not part of any product (Q27)."""

    line: int = Field(..., ge=1, description="The line's number in the prompt")
    kind: OtherLineKind = Field(..., description="What the line is")
    amount: float | None = Field(
        default=None, description="Signed amount printed on the line, if any"
    )


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
    other_lines: list[OtherLine] = Field(
        default_factory=list,
        description="Numbered lines accounted for as not products (Q27)",
    )
    receipt_total: float | None = Field(
        default=None, description="The receipt's grand total as printed (Q27)"
    )
    language: str | None = Field(
        default=None, description="ISO 639-1 language of the receipt, as detected"
    )
    country: str | None = Field(
        default=None,
        description="ISO 3166-1 alpha-2 country of the receipt, as detected",
    )
    invalid_entries: int = Field(
        default=0,
        ge=0,
        description="Entries the model returned that could not be used (Q27)",
    )
    raw_completion: str | None = Field(
        default=None,
        description="The model's answer as returned, capped; kept for diagnosis (Q27)",
    )
