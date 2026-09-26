"""Product icons the local model draws (Q18)

Every tile showed its category's emoji, so every fruit was an apple and all meat a steak. The
Q18 spike (docs/spikes/Q18_product_icons.md) had the model draw a flat 48x48 SVG per product,
and the operator ruled on 2026-09-26 that the drawing is stored in the database, not as files
on a volume: the sanitised drawings are under 1 KB, the database backup covers them, and a
pending drawing can be told apart from a failed one.

`icon_svg` holds the sanitised markup, `icon_status` says where the drawing stands (pending,
ready, failed, cleared), and `icon_updated_at` is when the markup last changed. All nullable
with no backfill: NULL is "no drawing, show the category emoji", which is how every existing
product already behaves. `scripts/backfill_icons.py` queues the drawings after deploy.

Revision ID: e4b8c1d7a236
Revises: 9c91d21d50ed
Create Date: 2026-09-26 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b8c1d7a236"
down_revision: str | Sequence[str] | None = "9c91d21d50ed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("product_master", sa.Column("icon_svg", sa.Text(), nullable=True))
    op.add_column(
        "product_master", sa.Column("icon_status", sa.String(), nullable=True)
    )
    op.add_column(
        "product_master",
        sa.Column("icon_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("product_master", "icon_updated_at")
    op.drop_column("product_master", "icon_status")
    op.drop_column("product_master", "icon_svg")
