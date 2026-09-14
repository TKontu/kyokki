"""Delete consumption history with its inventory item (MVP-S4)

Revision ID: d5f1b8c2e4a6
Revises: c3e9a7b5d1f2
Create Date: 2026-09-14 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d5f1b8c2e4a6"
down_revision: str | Sequence[str] | None = "c3e9a7b5d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "consumption_log_inventory_item_id_fkey"


def upgrade() -> None:
    op.drop_constraint(FK_NAME, "consumption_log", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME,
        "consumption_log",
        "inventory_item",
        ["inventory_item_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "consumption_log", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME, "consumption_log", "inventory_item", ["inventory_item_id"], ["id"]
    )
