from sqlalchemy import Column, String, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.db.base_class import Base


class ShoppingListItem(Base):
    """Items to purchase, either manually added or auto-generated.

    Supports both linked products (product_master_id) and free-text items.
    Tracks priority and source for smart shopping list management.
    """

    __tablename__ = "shopping_list_item"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_master_id = Column(
        UUID(as_uuid=True), ForeignKey("product_master.id"), nullable=True, index=True
    )  # NULL for free-text items

    # Item details
    name = Column(String, nullable=False)  # Display name
    quantity = Column(Numeric(10, 2), nullable=False)
    unit = Column(String, nullable=False)

    # Organization
    priority = Column(String, nullable=False, default="normal", index=True)  # urgent, normal, low
    source = Column(String, nullable=False, default="manual", index=True)  # manual, auto_restock, recipe

    # Purchase tracking
    is_purchased = Column(Boolean, nullable=False, default=False, index=True)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    purchased_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    product_master = relationship("ProductMaster", back_populates="shopping_list_items")
