"""Split items off a product, and undo it (CL8 L0 + L2)

Adds the item provenance columns the identity lane fills in (`receipt_line_id`,
`join_source`, `join_key`) and the `product_reassignment` table a split records itself in,
so it can be undone. `receipt_line_id` is backfilled from the receipt's stored lines through
`receipt_line_index`, wherever that line carries a well-formed `line_id`.

Revision ID: e2a9c4f71b38
Revises: d8f3a61c2b57
Create Date: 2026-10-06 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2a9c4f71b38"
down_revision: str | Sequence[str] | None = "d8f3a61c2b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_PATTERN = (
    "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# The line at the item's raw position, when the receipt still has one with a UUID line_id.
BACKFILL = sa.text(
    """
    UPDATE inventory_item AS item
    SET receipt_line_id = CAST(
        receipt.ocr_structured -> 'lines' -> item.receipt_line_index ->> 'line_id' AS uuid
    )
    FROM receipt
    WHERE item.receipt_id = receipt.id
      AND item.receipt_line_index IS NOT NULL
      AND item.receipt_line_id IS NULL
      AND jsonb_typeof(receipt.ocr_structured -> 'lines') = 'array'
      AND (receipt.ocr_structured -> 'lines' -> item.receipt_line_index ->> 'line_id')
          ~ :pattern
    """
)


def backfill(conn: sa.engine.Connection) -> None:
    """Fill `receipt_line_id` from the stored line at `receipt_line_index`."""
    conn.execute(BACKFILL, {"pattern": UUID_PATTERN})


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inventory_item",
        sa.Column("receipt_line_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "inventory_item", sa.Column("join_source", sa.String(), nullable=True)
    )
    op.add_column("inventory_item", sa.Column("join_key", sa.String(), nullable=True))

    op.create_table(
        "product_reassignment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_created", sa.Boolean(), nullable=False),
        sa.Column("item_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["from_product_id"], ["product_master.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["to_product_id"], ["product_master.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_reassignment_id"), "product_reassignment", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_product_reassignment_from_product_id"),
        "product_reassignment",
        ["from_product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_product_reassignment_to_product_id"),
        "product_reassignment",
        ["to_product_id"],
        unique=False,
    )

    backfill(op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_product_reassignment_to_product_id"),
        table_name="product_reassignment",
    )
    op.drop_index(
        op.f("ix_product_reassignment_from_product_id"),
        table_name="product_reassignment",
    )
    op.drop_index(op.f("ix_product_reassignment_id"), table_name="product_reassignment")
    op.drop_table("product_reassignment")
    op.drop_column("inventory_item", "join_key")
    op.drop_column("inventory_item", "join_source")
    op.drop_column("inventory_item", "receipt_line_id")
