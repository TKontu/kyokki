"""Remember which Telegram chat is owed which receipt's result (CL5)

The bot's result notifier kept this in memory, so a restart lost the edit of a pending
"Received" message, and receipts from e-mail or the watched folder never reached Telegram.
One row per (receipt, chat); ``notified_at`` is set once the result was delivered.

Revision ID: d8f3a61c2b57
Revises: c9a51b6756c1
Create Date: 2026-10-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8f3a61c2b57"
down_revision: str | Sequence[str] | None = "c9a51b6756c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "telegram_receipt_message",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipt.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("receipt_id", "chat_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("telegram_receipt_message")
