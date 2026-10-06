"""The read-only product-join audit (CL8 L4): `GET /api/audit/product-joins`."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditPrintedGroup(BaseModel):
    """A product's receipt-born items that share one (chain, normalised printed name)."""

    label: str = Field(description="The normalised printed name")
    store_chain: str | None = None
    match_sources: list[str] = Field(
        default_factory=list,
        description="How these lines were resolved: alias, name, selected, none",
    )
    generic_names: list[str] = Field(
        default_factory=list, description="The generic names the lines were read as"
    )
    active_count: int = Field(description="Items not yet used up or thrown away")
    total_count: int
    first_seen: date | None = None
    last_seen: date | None = None


class AuditedProduct(BaseModel):
    """A product whose items may have been joined wrongly, for the cook to review."""

    product_id: UUID
    product_name: str
    groups: list[AuditPrintedGroup]
    reasons: list[str]
    min_similarity: float | None = Field(
        None,
        description=(
            "Lowest pairwise similarity (0-1) between the printed groups, used only to "
            "rank; null with a single group"
        ),
    )


class AuditModelName(BaseModel):
    """A product name the model taught: a lookup key that no person confirmed."""

    id: UUID
    name: str
    product_id: UUID
    product_name: str
    item_count: int = Field(description="Inventory items the product holds")
    created_at: datetime


class AuditUnverifiedAlias(BaseModel):
    """A printed-name alias the cook has not verified."""

    id: UUID
    store_chain: str
    receipt_name: str
    product_id: UUID
    product_name: str
    source: str
    occurrence_count: int
    last_seen: datetime


class ProductJoinAudit(BaseModel):
    """The whole audit: flagged products (most suspicious first), model names, aliases."""

    products: list[AuditedProduct]
    model_names: list[AuditModelName]
    unverified_aliases: list[AuditUnverifiedAlias]
