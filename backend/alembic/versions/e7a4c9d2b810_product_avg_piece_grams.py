"""Average grams per piece, so weighed produce can be counted (Q2)

Revision ID: e7a4c9d2b810
Revises: d5f1b8c2e4a6
Create Date: 2026-09-17 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a4c9d2b810"
down_revision: str | Sequence[str] | None = "d5f1b8c2e4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable with no backfill: NULL means "no piece weight known", which is exactly how
    # every existing product already behaves.
    op.add_column(
        "product_master",
        sa.Column("avg_piece_grams", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("product_master", "avg_piece_grams")
