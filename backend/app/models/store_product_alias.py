from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.db.base_class import Base


class StoreProductAlias(Base):
    """Store-specific product name mappings for receipt parsing.

    Maps how different stores name products on receipts to the canonical
    product master. Tracks confidence and learning from manual corrections.
    """

    __tablename__ = "store_product_alias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_master_id = Column(UUID(as_uuid=True), ForeignKey("product_master.id"), nullable=False, index=True)

    # Store-specific identifiers
    store_chain = Column(String, nullable=False, index=True)  # s-market, prisma, k-citymarket, lidl
    receipt_name = Column(String, nullable=False, index=True)  # "VALIO MAITO 1L"
    barcode = Column(String, nullable=True, index=True)  # EAN-13, UPC, GS1 GTIN

    # Learning & verification
    confidence_score = Column(Float, nullable=False, default=0.0)  # 0.0-1.0
    manually_verified = Column(Boolean, nullable=False, default=False)
    occurrence_count = Column(Integer, nullable=False, default=1)
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    product_master = relationship("ProductMaster", back_populates="store_aliases")
