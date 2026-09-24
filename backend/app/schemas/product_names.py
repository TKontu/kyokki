"""The names a product answers to, as the product editor lists them (H52)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.product_name import NameSource


class ProductNameEntry(BaseModel):
    """A catalog name that resolves to the product (`product_name`)."""

    id: UUID
    name: str = Field(
        ..., description="The normalised key: casefolded, spaces collapsed"
    )
    source: NameSource = Field(
        ...,
        description="canonical (its own name), cook, or model (an unverified guess)",
    )
    removable: bool = Field(
        ..., description="False for the canonical name, which a rename changes instead"
    )


class PrintedNameEntry(BaseModel):
    """A receipt's printed name that resolves to the product (`store_product_alias`)."""

    id: UUID
    store_chain: str
    receipt_name: str
    source: str = Field(..., description="cook, model or name: who taught it")
    verified: bool = Field(
        ..., description="The cook confirmed it, rather than kept it"
    )
    occurrence_count: int
    last_seen: datetime | None = None


class ProductNamesResponse(BaseModel):
    """Everything that makes a line resolve to this product without asking the model."""

    names: list[ProductNameEntry]
    printed: list[PrintedNameEntry]
