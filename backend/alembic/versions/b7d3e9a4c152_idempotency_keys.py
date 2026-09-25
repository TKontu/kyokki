"""Remember responses to retried agent requests (AG2)

`Idempotency-Key` on the agent's stock routes: the first response to a key is stored and
replayed for 24 hours, so a retry after a lost response does not consume twice.

Revision ID: b7d3e9a4c152
Revises: e8b4f1c62a90
Create Date: 2026-09-25 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7d3e9a4c152"
down_revision: str | Sequence[str] | None = "e8b4f1c62a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "idempotency_key",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("route", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "route", name="uq_idempotency_key_key_route"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("idempotency_key")
