"""A confirmed emoji proposal, remembered by generic name (Q18 build).

The curated table (`app/resources/emoji_curated.json`) is read-only. Once a person confirms
the model's proposal for a generic name the table did not know, that name must never be asked
again - not just for the product row that was confirmed, but for any later product created
under the same name (a merge that deletes the original, a product re-added after deletion).
`product_master.canonical_name` is unique while a product lives, which is why this needs its
own table rather than a flag on the row: the row a proposal was confirmed on may not be the
row a later lookup is asking about.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class ProductEmojiLearned(Base):
    """One generic name a person has confirmed the exact emoji for."""

    __tablename__ = "product_emoji_learned"
    __table_args__ = (
        UniqueConstraint("generic_name", name="uq_product_emoji_learned_generic_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    # The lookup key: `normalize_product_name` (casefolded, whitespace collapsed).
    generic_name = Column(String, nullable=False, index=True)
    emoji = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
