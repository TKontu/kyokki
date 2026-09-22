"""The waste record outlives the item it describes

Deleting an item deleted its consumption log with it (`ON DELETE CASCADE`), so every metric
built on that log would quietly miss whatever had been deleted - a mistyped row cleared out of
the way takes real waste with it. The operator asked for the history to be kept for good
(2026-09-22), so the foreign key becomes `ON DELETE SET NULL` and the row stays behind.

A detached row still has to be readable, and `250` means nothing without a unit it can no
longer reach through the item. `unit` is therefore copied onto the row, backfilled from the
item it belongs to.

H22 owns the delete rules in general; this one is settled here because the metrics need it.

Revision ID: a3f7b21c6d40
Revises: f6c2d8e1a947
Create Date: 2026-09-22 20:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f7b21c6d40"
down_revision: str | Sequence[str] | None = "f6c2d8e1a947"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

FK_NAME = "consumption_log_inventory_item_id_fkey"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("consumption_log", sa.Column("unit", sa.String(), nullable=True))
    filled = (
        op.get_bind()
        .execute(
            sa.text(
                "UPDATE consumption_log AS cl SET unit = i.unit "
                "FROM inventory_item AS i WHERE i.id = cl.inventory_item_id"
            )
        )
        .rowcount
    )
    logger.info("unit: filled %s log rows from their item", filled)
    # Nothing to read it from for a row whose item is already gone; none can exist yet, since
    # deleting an item deleted its rows until now.
    op.execute("UPDATE consumption_log SET unit = 'pcs' WHERE unit IS NULL")
    op.alter_column("consumption_log", "unit", nullable=False)

    op.alter_column("consumption_log", "inventory_item_id", nullable=True)
    op.drop_constraint(FK_NAME, "consumption_log", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        "consumption_log",
        "inventory_item",
        ["inventory_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema. Rows whose item is already gone go with it: the old shape had no way
    to hold them."""
    op.execute("DELETE FROM consumption_log WHERE inventory_item_id IS NULL")
    op.drop_constraint(FK_NAME, "consumption_log", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        "consumption_log",
        "inventory_item",
        ["inventory_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("consumption_log", "inventory_item_id", nullable=False)
    op.drop_column("consumption_log", "unit")
