"""One general undo: what each log row overwrote, and which rows go together

`previous` is the item's undoable fields just before the event, so undo can put them back;
`batch_id` ties the rows of one action together, so a cleared shelf comes back in one step.

Existing rows get a batch of their own and no `previous`: nothing recorded what they
overwrote, and undo stops at them rather than guessing. The fresh-database redeploy makes that
moot.

Revision ID: f6c2d8e1a947
Revises: e4b9a7c2d815
Create Date: 2026-09-22 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6c2d8e1a947"
down_revision: str | Sequence[str] | None = "e4b9a7c2d815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "consumption_log",
        sa.Column(
            "batch_id",
            sa.UUID(),
            nullable=False,
            # Only to fill the existing rows; the application always sets its own
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.alter_column("consumption_log", "batch_id", server_default=None)
    op.create_index(
        op.f("ix_consumption_log_batch_id"),
        "consumption_log",
        ["batch_id"],
        unique=False,
    )
    op.add_column(
        "consumption_log",
        sa.Column("previous", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("consumption_log", "previous")
    op.drop_index(op.f("ix_consumption_log_batch_id"), table_name="consumption_log")
    op.drop_column("consumption_log", "batch_id")
