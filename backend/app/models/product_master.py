import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import deferred, relationship

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


class IconStatus(StrEnum):
    """Where a product's generated icon stands (Q18-G2). NULL in the column: never generated.

    Reused from the rejected SVG drawer (Q18, operator rejection 2026-09-27): the four states
    mean the same thing for a ComfyUI render as they did for a drawing.
    """

    PENDING = "pending"  # being generated, or waiting for the ComfyUI lock
    READY = "ready"
    FAILED = "failed"  # the last render failed; any earlier image is kept
    CLEARED = (
        "cleared"  # the cook chose the category emoji; nothing generates on its own
    )


class EmojiMatch(StrEnum):
    """Where a product's exact Apple emoji stands (Q18 build). NULL: never looked up.

    The operator's rule (2026-09-27, docs/spikes/Q18_exact_emoji.md): a tile shows an emoji
    only when it is precise, so the closest match is never shown. The tile checks this value,
    not just whether `emoji` is set: a `proposed` row has an emoji column that must stay
    hidden until a person confirms it.
    """

    EXACT = "exact"  # the curated table, or a proposal a person confirmed
    PROPOSED = "proposed"  # the model's answer, not yet confirmed - never shown
    NONE = "none"  # on the gap list, or a rejected proposal
    COOK = "cook"  # set by hand; never overwritten by a table hit or a backfill
    CLEARED = "cleared"  # the cook chose no emoji; nothing proposes one again


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

    # The generated icon (Q18-G2): a small transparent PNG, downscaled from ComfyUI's fixed
    # 1024x1024 output to settings.ICON_IMAGE_SIZE for the tile. Deferred, so listing products
    # does not load it; only GET /products/{id}/icon.png reads it. Replaces the rejected
    # LLM-drawn SVG (`icon_svg`, operator rejection 2026-09-27) - downgrading the migration
    # that dropped it restores an empty column, not the drawings.
    icon_image = deferred(Column(LargeBinary, nullable=True))
    # The seed ComfyUI used for the stored image; NULL before the first generation.
    # Regenerate always picks a fresh random one (the operator's ask, 2026-09-30).
    icon_seed = Column(BigInteger, nullable=True)
    # pending (generating), ready, failed (kept any earlier image) or cleared (the cook chose
    # the category emoji; nothing generates it on its own). NULL: never generated.
    icon_status = Column(String, nullable=True)
    # When icon_image last changed; NULL exactly when there is no image to show.
    icon_updated_at = Column(DateTime(timezone=True), nullable=True)

    # The exact Apple emoji (Q18 build): one emoji from app/resources/emoji_reference.json,
    # or NULL. The tile only shows it when emoji_match is `exact` or `cook` - see EmojiMatch.
    emoji = Column(Text, nullable=True)
    emoji_match = Column(String, nullable=True)

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
    # Per-language display names (Post-MVP frontier item 13), read-only here: writes go
    # through crud.product_master.set_display_name, never through this collection. `lazy`
    # is "selectin" rather than the default - not a query-time choice made where the product
    # is loaded, but the mapper's own default, so it is there for every loader of a
    # ProductMaster regardless of which file wrote that query (notably
    # `crud/inventory_item.py`'s eager-load chain, owned by a sibling lane this round, which
    # cannot be asked to add an option for a relationship it does not know about).
    display_name_rows = relationship(
        "ProductDisplayName",
        back_populates="product_master",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    store_aliases = relationship("StoreProductAlias", back_populates="product_master")
    inventory_items = relationship("InventoryItem", back_populates="product_master")
    shopping_list_items = relationship(
        "ShoppingListItem", back_populates="product_master"
    )

    @property
    def icon_version(self) -> int | None:
        """Whole seconds of icon_updated_at, for the icon URL; None: no image to show."""
        updated = self.icon_updated_at
        return None if updated is None else int(updated.timestamp())

    @property
    def display_names(self) -> dict[str, str]:
        """Per-language display names (Post-MVP frontier item 13), by language code.

        English is never a key here: the canonical name already is the English name, and
        the frontend's `displayName.ts` falls back to it when a language has no row.
        """
        return {str(row.language): str(row.name) for row in self.display_name_rows}

    @property
    def display_name_sources(self) -> dict[str, str]:
        """Whose word each display name is (`cook` or `model`), by the same language code
        `display_names` uses - the product edit sheet marks a `model` row "proposed".
        """
        return {str(row.language): str(row.source) for row in self.display_name_rows}
