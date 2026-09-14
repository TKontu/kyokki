"""Add receipt queue columns: queued_at, processing_started_at, error (MVP-R3)

Revision ID: c3e9a7b5d1f2
Revises: b7d3e5f1a2c4
Create Date: 2026-09-14 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3e9a7b5d1f2"
down_revision: str | Sequence[str] | None = "b7d3e5f1a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipt", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "receipt",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("receipt", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("receipt", "error")
    op.drop_column("receipt", "processing_started_at")
    op.drop_column("receipt", "queued_at")
