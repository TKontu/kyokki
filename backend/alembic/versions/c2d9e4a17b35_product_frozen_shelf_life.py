"""Frozen life per product, the category's as the fallback (H52)

`b7e3d5c19f02` gave each category a frozen shelf life, and moving an item to the
freezer re-dates it from that (Q12, DEC-10). One number per category is too coarse:
bacon is meat but does not keep 180 days frozen, and a juice the cook freezes has no
category figure at all. The operator's ruling of 2026-09-24 puts it on the product.

Nullable with no backfill: NULL means "whatever the category says", which is how every
existing product already behaves.

Revision ID: c2d9e4a17b35
Revises: a3f7b21c6d40
Create Date: 2026-09-24 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d9e4a17b35"
down_revision: str | Sequence[str] | None = "a3f7b21c6d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "product_master",
        sa.Column("frozen_shelf_life_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("product_master", "frozen_shelf_life_days")
