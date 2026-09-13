"""Add unique constraint on product_master.off_product_id

The model gained ``uq_product_master_off_product_id`` in PR #21 without a
migration; tests (which use ``create_all``) had it while ``alembic upgrade head``
did not. CI now runs ``alembic check`` to catch this class of drift.

Revision ID: 7c1f2a9d4b30
Revises: c943e915cf61
Create Date: 2026-09-13 18:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1f2a9d4b30"
down_revision: str | Sequence[str] | None = "c943e915cf61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        "uq_product_master_off_product_id", "product_master", ["off_product_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_product_master_off_product_id", "product_master", type_="unique"
    )
