"""Every name that means one product: its canonical name and any learned synonym.

Identity is a key, not a score (`docs/PRODUCT_RESOLUTION_SPEC.md` §2). Fuzzy similarity
cannot see synonyms at all - "Minced beef" scores 64 against "Ground beef" - so the
catalog has to carry the names it knows rather than guess at them.

The canonical name is itself a row, so resolving a name is one query rather than a
lookup plus a fallback.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class NameSource(StrEnum):
    """Where a name came from. Only the cook's own actions produce `cook`.

    Was a bare tuple that nothing imported, while `services/product_names.learn_product_name`
    took a free `str` (H24).
    """

    CANONICAL = "canonical"
    COOK = "cook"
    MODEL = "model"


class ProductName(Base):
    """A name -> product mapping, unique across the catalog."""

    __tablename__ = "product_name"
    __table_args__ = (
        UniqueConstraint("name", name="uq_product_name_name"),
        # Trigram index for candidate shortlists (H13). Declared here as well as in the
        # migration so `create_all` builds it for the test database and `alembic check`
        # does not propose dropping it.
        Index(
            "ix_product_name_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_master_id = Column(
        UUID(as_uuid=True),
        # A name has no meaning without its product, so it goes when the product does.
        ForeignKey("product_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Normalised by services.product_names.normalize_product_name: casefolded, single spaces.
    name = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False, default="model")
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    product_master = relationship("ProductMaster", back_populates="names")

    def __repr__(self) -> str:
        return f"<ProductName {self.name!r} -> {self.product_master_id}>"
