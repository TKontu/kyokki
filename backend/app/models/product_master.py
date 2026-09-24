import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ShelfLifeSource(StrEnum):
    """Where a stored shelf life came from (Q11).

    `category` is the blanket figure creation falls back to when no estimate arrived - a
    placeholder, not an answer. Only the cook's own edit produces `cook`, and only `cook` is
    safe from a later estimate.

    This was a bare tuple that nothing imported: the field was enforced by a `Literal` on the
    *response* schema, so it validated on the way out and never on the way in (H24).
    """

    CATEGORY = "category"
    MODEL = "model"
    COOK = "cook"


class ProductMaster(Base):
    """Canonical product definition - the single source of truth for products.

    Each product master represents a unique product with its characteristics,
    storage requirements, and default shelf life.
    """

    __tablename__ = "product_master"
    __table_args__ = (
        UniqueConstraint("off_product_id", name="uq_product_master_off_product_id"),
        # One product per name, case- and space-insensitively (H11). A functional index,
        # declared here so `alembic check` does not propose dropping it every run.
        Index(
            "uq_product_master_canonical_name_lower",
            text("lower(btrim(canonical_name))"),
            unique=True,
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    canonical_name = Column(String, nullable=False, index=True)  # "Valio Whole Milk 1L"
    category = Column(String, ForeignKey("category.id"), nullable=False, index=True)
    storage_type = Column(String, nullable=False)  # refrigerator, freezer, pantry

    # Shelf life
    default_shelf_life_days = Column(Integer, nullable=False)  # unopened
    # Where that number came from (Q11). The column is NOT NULL, so creation has to
    # invent a value and `5` cannot otherwise be told apart from `5 because the meat
    # category says so`. Only `cook` is a correction and is never overwritten; a
    # `category` fallback is a placeholder a later estimate may replace.
    shelf_life_source = Column(
        String, nullable=False, default="category", server_default="category"
    )  # category, model, cook
    opened_shelf_life_days = Column(Integer, nullable=True)  # after opening
    # Days it keeps once frozen (H52). NULL defers to the category's figure; set when
    # the product keeps differently from its category - bacon is not a 180-day meat.
    frozen_shelf_life_days = Column(Integer, nullable=True)

    # Quantity tracking
    # What one of them weighs, roughly, when the shop sells it by weight but the cook counts
    # it in pieces (Q2). NULL means the idea does not apply - milk, washing-up liquid.
    avg_piece_grams = Column(Numeric(10, 2), nullable=True)
    # What one pack weighs, for a product measured by weight rather than counted
    # (Q8). The mirror of avg_piece_grams, and mutually exclusive with it in
    # practice: a thing is either counted or weighed.
    pack_grams = Column(Numeric(10, 2), nullable=True)
    unit_type = Column(String, nullable=False)  # volume, weight, count
    default_unit = Column(String, nullable=False)  # dl, tsp, tbsp, g, pcs (MVP-U1)
    default_quantity = Column(Numeric(10, 2), nullable=True)  # 1000, 500, 6

    # Auto-restock
    min_stock_quantity = Column(
        Numeric(10, 2), nullable=True
    )  # threshold for auto shopping list
    reorder_quantity = Column(Numeric(10, 2), nullable=True)  # how much to reorder

    # Open Food Facts integration
    off_product_id = Column(String, nullable=True, index=True)  # OFF barcode
    off_data = Column(JSONB, nullable=True)  # cached nutrition, image, etc.

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    category_rel = relationship("Category", foreign_keys=[category])
    names = relationship(
        "ProductName", back_populates="product_master", cascade="all, delete-orphan"
    )
    store_aliases = relationship("StoreProductAlias", back_populates="product_master")
    inventory_items = relationship("InventoryItem", back_populates="product_master")
    shopping_list_items = relationship(
        "ShoppingListItem", back_populates="product_master"
    )
