import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ConsumptionLog(Base):
    """History of an item's quantity, one row per event (H46).

    Each row can be read on its own: what happened (`action`), how much it moved
    (`quantity_consumed`, kept under its old name although a restore or a correction moves
    food the other way) and what was left (`quantity_after`), in the item's unit. Waste is the
    `discard` rows.

    Each row is also a step the general undo can take back: `previous` holds the item's fields
    as they were just before the event, and `batch_id` ties together the rows one action wrote,
    so a cleared shelf comes back in one step. `previous` is NULL on rows logged before undo
    existed; those cannot be undone.
    """

    __tablename__ = "consumption_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    inventory_item_id = Column(
        UUID(as_uuid=True),
        # Deleting an item (entered by mistake, MVP-S4) removes its history too
        ForeignKey("inventory_item.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_master_id = Column(
        UUID(as_uuid=True), ForeignKey("product_master.id"), nullable=False, index=True
    )

    action = Column(
        String, nullable=False, index=True
    )  # schemas.consumption_log.ConsumptionAction
    quantity_consumed = Column(Numeric(10, 2), nullable=False)
    quantity_after = Column(Numeric(10, 2), nullable=False)

    batch_id = Column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, index=True
    )
    previous = Column(JSONB, nullable=True)  # crud.inventory_item.snapshot

    logged_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # Relationships
    inventory_item = relationship("InventoryItem", back_populates="consumption_logs")
    product_master = relationship("ProductMaster")

    # Read-only details for API responses. Callers must eager-load inventory_item and
    # product_master (see crud.consumption_log.list_consumption_logs).
    @property
    def product_name(self) -> str:
        return str(self.product_master.canonical_name)

    @property
    def unit(self) -> str:
        return str(self.inventory_item.unit)
