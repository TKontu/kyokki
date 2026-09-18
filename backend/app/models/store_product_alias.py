import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class StoreProductAlias(Base):
    """Store-specific product name mappings for receipt parsing.

    Maps how different stores name products on receipts to the canonical
    product master. Tracks confidence and learning from manual corrections.
    """

    __tablename__ = "store_product_alias"
    __table_args__ = (
        # One mapping per printed name per chain. Enforced only by a SELECT-then-insert
        # in confirm before H14, so two concurrent confirms could duplicate the row.
        UniqueConstraint(
            "store_chain", "receipt_name", name="uq_store_product_alias_chain_name"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_master_id = Column(
        UUID(as_uuid=True), ForeignKey("product_master.id"), nullable=False, index=True
    )

    # Store-specific identifiers
    store_chain = Column(
        String, nullable=False, index=True
    )  # s-market, prisma, k-citymarket, lidl
    receipt_name = Column(String, nullable=False, index=True)  # "VALIO MAITO 1L"
    barcode = Column(String, nullable=True, index=True)  # EAN-13, UPC, GS1 GTIN

    # Learning & verification
    # Where the mapping came from: `cook` (the cook chose or corrected it), `model`
    # (a constrained selection), `name` (a catalog name matched). Only `cook` is
    # verified memory - docs/PRODUCT_RESOLUTION_SPEC.md §3.4.
    source = Column(String, nullable=False, default="cook")
    confidence_score = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    manually_verified = Column(Boolean, nullable=False, default=False)
    occurrence_count = Column(Integer, nullable=False, default=1)
    last_seen = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    product_master = relationship("ProductMaster", back_populates="store_aliases")
