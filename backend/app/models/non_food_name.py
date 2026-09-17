"""Printed names the cook has said are not food (Q1)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class NonFoodName(Base):
    """A receipt line name that should not be offered as food again.

    Deliberately not a ``store_product_alias``: that table points at a product, and a towel has
    none. Keyed the same way though - the normalised printed name and the store chain - so the
    two agree on what "the same line" means.
    """

    __tablename__ = "non_food_name"
    __table_args__ = (
        UniqueConstraint("store_chain", "receipt_name", name="uq_non_food_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    store_chain = Column(String, nullable=False, index=True)
    receipt_name = Column(String, nullable=False, index=True)
    times_seen = Column(Integer, nullable=False, default=1)
    last_seen = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
