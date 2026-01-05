from sqlalchemy import Column, String, Integer, DateTime, Date, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.db.base_class import Base


class Receipt(Base):
    """Receipt processing tracking and OCR results.

    Stores receipt images, OCR results, and processing status for
    batch receipt scanning workflow.
    """

    __tablename__ = "receipt"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    store_chain = Column(String, nullable=True, index=True)  # Detected or manual
    purchase_date = Column(Date, nullable=True)

    # OCR processing
    image_path = Column(String, nullable=False)  # Path to receipt image
    ocr_raw_text = Column(Text, nullable=True)  # Raw OCR output
    ocr_structured = Column(JSONB, nullable=True)  # Parsed items and metadata

    # Processing status
    processing_status = Column(
        String, nullable=False, default="queued", index=True
    )  # queued, processing, completed, failed
    batch_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Multi-receipt batch

    # Statistics
    items_extracted = Column(Integer, nullable=False, default=0)
    items_matched = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    inventory_items = relationship("InventoryItem", back_populates="receipt")
