"""A record of items moved from one product to another, so the move can be undone (CL8).

`docs/PRODUCT_IDENTITY_SPEC.md`, "Undoing a wrong join: split". One row per split: which
items moved, between which products, and every key the move changed together with what it
was before, which is everything `services.product_split.undo_split` needs to replay it
backwards.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base_class import Base


# `Base` is `declarative_base()`, typed Any: the [misc] every model here carries.
class ProductReassignment(Base):  # type: ignore[misc]
    __tablename__ = "product_reassignment"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # SET NULL: the record outlives a product deleted later (an undo deletes the product a
    # split created); a record with a side gone can no longer be undone.
    from_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_master.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    to_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_master.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    #: The target was created by this split (and is deleted by its undo when unused).
    target_created = Column(Boolean, nullable=False, default=False)
    #: The moved inventory item ids, as strings.
    item_ids = Column(JSONB, nullable=False)
    #: What the move changed, with the previous values: `aliases`, `names`, `shelf_lives`.
    keys = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    undone_at = Column(DateTime(timezone=True), nullable=True)
