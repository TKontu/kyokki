"""Exact Apple emoji or none, and the gap list (Q18 build)

Every tile showed its category's emoji, so every fruit was an apple. The operator ruled on
2026-09-27 (docs/spikes/Q18_exact_emoji.md) that a tile shows an emoji only when one is exact:
a curated table decides most products, the model only proposes for a name the table does not
know, and non-food gets nothing at all.

`emoji` is nullable text, one emoji from `app/resources/emoji_reference.json`. `emoji_match`
says whether it counts: `exact` (the curated table, or a confirmed proposal), `proposed` (the
model's answer, never shown until a person confirms it), `none` (the gap list, or a rejected
proposal), `cook` (set by hand, never overwritten) or `cleared` (the cook chose no emoji).
Both are NULL with no backfill: NULL means "never looked up", which is how every existing
product already behaves - the tile still falls back to the category emoji.
`scripts/backfill_emoji.py` applies the curated table to the existing catalog after deploy.

`product_emoji_learned` remembers a confirmed proposal by generic name (case- and
space-insensitive), so the same name is never asked again even for a later product created
under it - `product_master.canonical_name` is unique only while a product lives.

Revision ID: fbf2c08da52d
Revises: e4b8c1d7a236
Create Date: 2026-09-30 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fbf2c08da52d"
down_revision: str | Sequence[str] | None = "e4b8c1d7a236"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("product_master", sa.Column("emoji", sa.Text(), nullable=True))
    op.add_column(
        "product_master", sa.Column("emoji_match", sa.String(), nullable=True)
    )
    op.create_table(
        "product_emoji_learned",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generic_name", sa.String(), nullable=False),
        sa.Column("emoji", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "generic_name", name="uq_product_emoji_learned_generic_name"
        ),
    )
    op.create_index(
        op.f("ix_product_emoji_learned_id"), "product_emoji_learned", ["id"]
    )
    op.create_index(
        op.f("ix_product_emoji_learned_generic_name"),
        "product_emoji_learned",
        ["generic_name"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_product_emoji_learned_generic_name"),
        table_name="product_emoji_learned",
    )
    op.drop_index(
        op.f("ix_product_emoji_learned_id"), table_name="product_emoji_learned"
    )
    op.drop_table("product_emoji_learned")
    op.drop_column("product_master", "emoji_match")
    op.drop_column("product_master", "emoji")
