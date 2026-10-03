import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

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
    priority = Column(
        String, nullable=False, default="normal", index=True
    )  # urgent, normal, low
    source = Column(
        String, nullable=False, default="manual", index=True
    )  # manual, auto_restock, recipe

    # Purchase tracking
    is_purchased = Column(Boolean, nullable=False, default=False, index=True)
    added_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    purchased_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships. `lazy="selectin"`: a row carries its product's display names
    # (`product_display_names` below) whether it reaches the API through the list
    # endpoint's own `joinedload` (crud.shopping_list_item.get_all) or through a plain
    # `get`/`update` elsewhere - the default strategy loads it either way, in one extra
    # query for the whole batch rather than per row (same reasoning as
    # `ProductMaster.display_name_rows`, see its own `lazy="selectin"`).
    product_master = relationship(
        "ProductMaster", back_populates="shopping_list_items", lazy="selectin"
    )

    # Read-only for API responses. A free-text item (no product_master_id) carries no
    # names to show, so the map is empty rather than raising on a null relationship.
    @property
    def product_display_names(self) -> dict[str, str]:
        """The linked product's per-language names (Post-MVP frontier item 13, phase 2),
        by language code; empty for a free-text item, one whose product has none, or -
        deliberately - one whose own `name` the cook has edited away from the product's
        canonical name. `name` is free text the cook can retype at will (unlike
        `InventoryItem`, which has no editable name of its own); a row carries this map
        only while `name` still reads as the product put it, so the frontend's own
        `displayName()` falling back to `name` keeps the cook's own wording rather than
        overwriting it with a translation of a product they have since renamed.
        """
        if self.product_master is None:
            return {}
        if str(self.name) != str(self.product_master.canonical_name):
            return {}
        return cast(dict[str, str], self.product_master.display_names)
