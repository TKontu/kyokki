"""Inventory item's receipt line (Q26)

The item had `receipt_id`, but not which printed line on that receipt it came from, so "fish
soup" could not be traced back to "KOKKIKARTANO KERMAINEN LOHIKEITTO". `receipt_line_index` is
the line's raw position in `receipt.ocr_structured`'s line list - the same position
`ExtractedItem.index` already sends the client, named as its own column here because
`ocr_structured` itself can later be re-read differently; `receipt_line_text` is the printed
name as read, kept alongside the index so the item's sheet still reads right even then.

Both nullable, with no backfill: a hand-added item, or one confirmed before this column
existed, simply has neither - the sheet shows the receipt without the line.

Revision ID: f1a2b3c4d5e6
Revises: e4b8c1d7a236
Create Date: 2026-09-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e4b8c1d7a236"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inventory_item", sa.Column("receipt_line_index", sa.Integer(), nullable=True)
    )
    op.add_column(
        "inventory_item", sa.Column("receipt_line_text", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("inventory_item", "receipt_line_text")
    op.drop_column("inventory_item", "receipt_line_index")
