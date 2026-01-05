from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.db.base_class import Base


class ConsumptionLog(Base):
    """History of product consumption and adjustments.

    Tracks when and how items are used, enabling usage patterns
    and waste reduction insights.
    """

    __tablename__ = "consumption_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    inventory_item_id = Column(UUID(as_uuid=True), ForeignKey("inventory_item.id"), nullable=False, index=True)
    product_master_id = Column(UUID(as_uuid=True), ForeignKey("product_master.id"), nullable=False, index=True)

    # Action tracking
    action = Column(String, nullable=False, index=True)  # use_partial, use_full, discard, adjust
    quantity_consumed = Column(Numeric(10, 2), nullable=False)
    consumption_context = Column(
        String, nullable=True, index=True
    )  # breakfast, lunch, dinner, snack, cooking

    logged_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    inventory_item = relationship("InventoryItem", back_populates="consumption_logs")
    product_master = relationship("ProductMaster")
