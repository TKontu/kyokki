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
        # The record outlives the item (operator, 2026-09-22): deleting an item used to delete
        # what it wasted with it, and the waste metrics would then be quietly short. The row
        # keeps its own `unit`, so a detached one still says what 250 of something means.
        ForeignKey("inventory_item.id", ondelete="SET NULL"),
        nullable=True,
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
    unit = Column(
        String, nullable=False
    )  # The item's unit, copied so the row can stand alone

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
    def item_status(self) -> str | None:
        """Where the item stands now, or None once it has been deleted.

        What tells the Gone screen whether this row can still be put back.
        """
        return None if self.inventory_item is None else str(self.inventory_item.status)
