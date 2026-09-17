"""Remember printed names that are not food (Q1)

Revision ID: f3b8c1d4e207
Revises: e7a4c9d2b810
Create Date: 2026-09-17 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3b8c1d4e207"
down_revision: str | Sequence[str] | None = "e7a4c9d2b810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "non_food_name",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_chain", sa.String(), nullable=False),
        sa.Column("receipt_name", sa.String(), nullable=False),
        sa.Column("times_seen", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_chain", "receipt_name", name="uq_non_food_name"),
    )
    op.create_index(op.f("ix_non_food_name_id"), "non_food_name", ["id"])
    op.create_index(
        op.f("ix_non_food_name_store_chain"), "non_food_name", ["store_chain"]
    )
    op.create_index(
        op.f("ix_non_food_name_receipt_name"), "non_food_name", ["receipt_name"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_non_food_name_receipt_name"), table_name="non_food_name")
    op.drop_index(op.f("ix_non_food_name_store_chain"), table_name="non_food_name")
    op.drop_index(op.f("ix_non_food_name_id"), table_name="non_food_name")
    op.drop_table("non_food_name")
