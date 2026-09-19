"""Grams in one pack, so a counted line can be weighed (Q8)

The mirror of `avg_piece_grams` (`e7a4c9d2b810`). That one turns a weighed line into
pieces because the shop weighs apples and the cook eats them one at a time; this one
turns a counted line into grams because the shop counts packs of mince and the cook
wants to know there is 400 g in the freezer.

Nullable with no backfill: NULL means "no pack weight known", which is how every
existing product already behaves. The value is filled from a size printed in the
product name (`SIPULI 500G`) or by the cook in the product editor - **not** by the
model, which was offered a `pk` field and answered on 1 line of 49 while dragging the
other per-line estimates down with it (docs/vLLM_MANUAL_TEST.md).

Revision ID: d1a7f4b62e93
Revises: c8e5a30f172b
Create Date: 2026-09-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1a7f4b62e93"
down_revision: str | Sequence[str] | None = "c8e5a30f172b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "product_master",
        sa.Column("pack_grams", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("product_master", "pack_grams")
