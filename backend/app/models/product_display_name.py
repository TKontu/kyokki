"""A product's name in a display language, alongside - never instead of - its canonical
English name (Post-MVP frontier item 13).

Operator ruling (2026-10-02): "the system should have selectable display language. But of
course if the receipts are finnish the input data should kept as original." Products are
generic and English since MVP-R2 (`product_master.canonical_name`); this table adds an
optional per-language name the cook sees instead, when a language other than English is
chosen (`frontend/lib/language.ts`). English always shows the canonical name, never a row
here.

This is deliberately **not** `product_name` (`domain/product_names.py`): that table is the
resolution key a receipt line matches against, one row per unique name, enforced by a
catalog-wide unique index. A display name is neither unique across products (two products may
both be "Maito" in Finnish) nor a key anything resolves by - it is read, never matched.

One row per (product, language); `source` is `cook` (typed by hand, PATCH /products/{id}) or
`model` (proposed in the background when the product is created, next to its shelf-life
estimate - `services/shelf_life_on_create.py`, `services/display_names.py`). A `cook` row is
never overwritten by a later proposal.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class DisplayNameSource(StrEnum):
    """Whose word a display name is. Only the cook's own edit produces `cook`, and only
    `cook` is safe from a later model proposal (mirrors `ShelfLifeSource`, H24's lesson)."""

    MODEL = "model"
    COOK = "cook"


class ProductDisplayName(Base):
    """One product's name in one language, besides its canonical English name."""

    __tablename__ = "product_display_name"
    __table_args__ = (
        UniqueConstraint(
            "product_master_id",
            "language",
            name="uq_product_display_name_product_language",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_master_id = Column(
        UUID(as_uuid=True),
        # A display name has no meaning without its product, so it goes when the product does.
        ForeignKey("product_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # An ISO 639-1 code, e.g. "fi". Not an enum: the spec asks the code to allow more than the
    # one language Phase 1 ships (`services/display_names.SUPPORTED_LANGUAGES`).
    language = Column(String, nullable=False)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False, default="model")
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    product_master = relationship("ProductMaster", back_populates="display_name_rows")

    def __repr__(self) -> str:
        return f"<ProductDisplayName {self.language!r}={self.name!r} -> {self.product_master_id}>"
