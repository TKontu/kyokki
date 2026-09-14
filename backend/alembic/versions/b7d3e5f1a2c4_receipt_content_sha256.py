"""Add receipt.content_sha256 for duplicate upload detection (MVP-T1)

Revision ID: b7d3e5f1a2c4
Revises: a4f8c2d91e37
Create Date: 2026-09-14 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3e5f1a2c4"
down_revision: str | Sequence[str] | None = "a4f8c2d91e37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipt", sa.Column("content_sha256", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_receipt_content_sha256"), "receipt", ["content_sha256"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_receipt_content_sha256"), table_name="receipt")
    op.drop_column("receipt", "content_sha256")
