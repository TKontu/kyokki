"""A per-language display name on the product (Post-MVP frontier item 13)

Operator ruling (2026-10-02): "the system should have selectable display language. But of
course if the receipts are finnish the input data should kept as original." Products are
generic and English since MVP-R2 (`product_master.canonical_name`); the cook can now pick a
display language in Settings and see each product's name in it, falling back to the English
canonical name when none is set.

A new table, `product_display_name`, over a JSONB column on `product_master`: a JSONB blob
reads as "the whole thing or nothing" to the ORM, so every write - the cook's own edit, and
the model's background proposal for a brand-new product - would have to read-modify-write the
entire dict under a lock to avoid one clobbering the other's language; a dedicated row per
(product, language) lets Postgres's own unique index settle that instead, the same trade this
catalog already made for synonyms (`product_name`, one row per name) rather than an array
column. It also keeps `source` (`cook` | `model`) per language, not just per product, which a
single JSONB value cannot without inventing its own shape for provenance.

One row per (product, language); `ondelete="CASCADE"` so a deleted product takes its display
names with it, as `product_name` already does. No backfill: NULL rows (no entry at all) are
exactly what every existing product already shows - the English canonical name - and
`scripts/backfill_display_names.py` proposes Finnish names for them after deploy, the same
shape as `scripts/backfill_emoji.py`.

These are **not** resolution keys: `product_name` (and `services/product_names.py`) is
untouched by this migration, and a receipt line still resolves only through the canonical
name and its learned synonyms.

Revision ID: 61f6f69cc22f
Revises: c715f1ea4510
Create Date: 2026-10-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "61f6f69cc22f"
down_revision: str | Sequence[str] | None = "c715f1ea4510"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "product_display_name",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_master_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_master_id"], ["product_master.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_master_id",
            "language",
            name="uq_product_display_name_product_language",
        ),
    )
    op.create_index(op.f("ix_product_display_name_id"), "product_display_name", ["id"])
    op.create_index(
        op.f("ix_product_display_name_product_master_id"),
        "product_display_name",
        ["product_master_id"],
    )


def downgrade() -> None:
    """Downgrade schema. Drops the table - a cook-typed Finnish name is not recoverable."""
    op.drop_index(
        op.f("ix_product_display_name_product_master_id"),
        table_name="product_display_name",
    )
    op.drop_index(op.f("ix_product_display_name_id"), table_name="product_display_name")
    op.drop_table("product_display_name")
