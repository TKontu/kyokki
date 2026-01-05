from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from app.db.base_class import Base


class ProductMaster(Base):
    """Canonical product definition - the single source of truth for products.

    Each product master represents a unique product with its characteristics,
    storage requirements, and default shelf life.
    """

    __tablename__ = "product_master"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    canonical_name = Column(String, nullable=False, index=True)  # "Valio Whole Milk 1L"
    category = Column(String, ForeignKey("category.id"), nullable=False, index=True)
    storage_type = Column(String, nullable=False)  # refrigerator, freezer, pantry

    # Shelf life
    default_shelf_life_days = Column(Integer, nullable=False)  # unopened
    opened_shelf_life_days = Column(Integer, nullable=True)  # after opening

    # Quantity tracking
    unit_type = Column(String, nullable=False)  # volume, weight, count, unit
    default_unit = Column(String, nullable=False)  # ml, g, pcs
    default_quantity = Column(Numeric(10, 2), nullable=True)  # 1000, 500, 6

    # Auto-restock
    min_stock_quantity = Column(Numeric(10, 2), nullable=True)  # threshold for auto shopping list
    reorder_quantity = Column(Numeric(10, 2), nullable=True)  # how much to reorder

    # Open Food Facts integration
    off_product_id = Column(String, nullable=True, index=True)  # OFF barcode
    off_data = Column(JSONB, nullable=True)  # cached nutrition, image, etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    category_rel = relationship("Category", foreign_keys=[category])
    store_aliases = relationship("StoreProductAlias", back_populates="product_master")
    inventory_items = relationship("InventoryItem", back_populates="product_master")
    shopping_list_items = relationship("ShoppingListItem", back_populates="product_master")
