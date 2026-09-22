"""A consumption history that can be read back (H46)

Every log row now says what was left after it (`quantity_after`), so a row can be read on its
own and a correction upward can be told from one downward. Rows are also written for `restore`
and `correct` from this revision on; that is code, not schema.

**The backfill is exact where it can be and says so where it cannot.** `use_full` and
`discard` leave nothing, so theirs is 0. A `use_partial` row gets the item's current quantity
plus everything consumed from it afterwards - exact unless the cook corrected the quantity by
hand at some point, which was never logged and so cannot be undone here. The operator's next
deploy starts from fresh databases, so this only has to be sensible, not perfect.

Discard rows of 0 - an item already finished and then cleared - are deleted: nothing was thrown
away, and the code no longer writes them.

`consumption_log.consumption_context` and `category.meal_contexts` are dropped. Nothing ever
wrote the first or read the second (F2, "dead fields"); a meal context can come back with the
thing that records it (`docs/TODO.md`, post-MVP 8).

Revision ID: e4b9a7c2d815
Revises: b7e3d5c19f02
Create Date: 2026-09-22 10:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b9a7c2d815"
down_revision: str | Sequence[str] | None = "b7e3d5c19f02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    deleted = connection.execute(
        sa.text(
            "DELETE FROM consumption_log "
            "WHERE action = 'discard' AND quantity_consumed = 0"
        )
    ).rowcount
    logger.info("Deleted %s zero-quantity discard rows", deleted)

    op.add_column(
        "consumption_log",
        sa.Column("quantity_after", sa.Numeric(10, 2), nullable=True),
    )
    connection.execute(
        sa.text(
            "UPDATE consumption_log SET quantity_after = 0 "
            "WHERE action IN ('use_full', 'discard')"
        )
    )
    # What was left after a helping is what is left now, plus every helping taken since
    connection.execute(
        sa.text(
            """
            UPDATE consumption_log AS cl
            SET quantity_after = i.current_quantity + COALESCE((
                SELECT SUM(later.quantity_consumed)
                FROM consumption_log AS later
                WHERE later.inventory_item_id = cl.inventory_item_id
                  AND later.action IN ('use_partial', 'use_full')
                  AND later.logged_at > cl.logged_at
            ), 0)
            FROM inventory_item AS i
            WHERE i.id = cl.inventory_item_id AND cl.quantity_after IS NULL
            """
        )
    )
    # Anything left over carried an action nothing ever wrote; 0 is as good as any guess
    connection.execute(
        sa.text(
            "UPDATE consumption_log SET quantity_after = 0 WHERE quantity_after IS NULL"
        )
    )
    op.alter_column("consumption_log", "quantity_after", nullable=False)

    op.drop_index(
        op.f("ix_consumption_log_consumption_context"), table_name="consumption_log"
    )
    op.drop_column("consumption_log", "consumption_context")
    op.drop_column("category", "meal_contexts")


def downgrade() -> None:
    """Downgrade schema. The dropped columns come back empty: nothing ever filled them."""
    op.add_column(
        "category",
        sa.Column("meal_contexts", sa.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "consumption_log",
        sa.Column("consumption_context", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_consumption_log_consumption_context"),
        "consumption_log",
        ["consumption_context"],
        unique=False,
    )
    op.drop_column("consumption_log", "quantity_after")
