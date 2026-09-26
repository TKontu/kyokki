"""A remembered response to a request an agent may retry (AG2).

An agent on a flaky connection cannot tell a lost request from a lost response, so it sends
the same ``Idempotency-Key`` again. The first response is kept here and replayed for 24 hours
instead of consuming the milk twice.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base_class import Base


class IdempotencyKey(Base):  # type: ignore[misc]  # Base is untyped until H21
    """One key's outcome on one route."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        UniqueConstraint("key", "route", name="uq_idempotency_key_key_route"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String, nullable=False)
    # The route template, e.g. "POST /api/stock/consume": the same key on two routes is two
    # different requests.
    route = Column(String, nullable=False)
    # sha256 hex of the canonical JSON of {path, body} (the validated body, every field),
    # to tell a retry from a reused key.
    request_hash = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    response = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<IdempotencyKey {self.route} {self.key!r}>"
