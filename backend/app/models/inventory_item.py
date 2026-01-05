from sqlalchemy import Column, String, Numeric, DateTime, Date, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.db.base_class import Base


class InventoryItem(Base):
    """Individual items in the refrigerator/freezer/pantry.

    Tracks quantity, expiry, and status of actual physical items.
    Uses approximate quantity tracking (1/4, 1/2, 3/4).
    """

    __tablename__ = "inventory_item"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_master_id = Column(UUID(as_uuid=True), ForeignKey("product_master.id"), nullable=False, index=True)
    receipt_id = Column(UUID(as_uuid=True), ForeignKey("receipt.id"), nullable=True, index=True)

    # Quantity (approximate tracking)
    initial_quantity = Column(Numeric(10, 2), nullable=False)
    current_quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String, nullable=False)  # ml, g, pcs, unit

    # Status
    status = Column(
        String, nullable=False, default="sealed", index=True
    )  # sealed, opened, partial, empty, discarded
    purchase_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=False, index=True)
    expiry_source = Column(String, nullable=False, default="calculated")  # scanned, calculated, manual
    opened_date = Column(Date, nullable=True)

    # Tracking
    batch_number = Column(String, nullable=True)  # From GS1 DataMatrix
    location = Column(String, nullable=False, default="main_fridge")  # main_fridge, freezer, pantry
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    product_master = relationship("ProductMaster", back_populates="inventory_items")
    receipt = relationship("Receipt", back_populates="inventory_items")
    consumption_logs = relationship("ConsumptionLog", back_populates="inventory_item")
