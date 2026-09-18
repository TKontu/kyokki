"""Alias provenance, and one alias per printed name per chain (H14)

`store_product_alias` recorded *that* a printed name maps to a product but not *how*
the mapping was made, so a guess and the cook's own correction were indistinguishable
- and confirm wrote `manually_verified=True` for both. `source` separates them:

    cook   the cook chose or corrected this mapping. Verified memory.
    model  a constrained selection the cook did not contradict.
    name   a catalog name matched the line; a key, not a judgement.

Backfilled from `manually_verified`, which is the only signal the old rows carry. Every
alias the old confirm wrote is `manually_verified=True`, so nearly all become `cook`;
that is the honest reading, because the cook did include those lines.

Uniqueness on (store_chain, receipt_name) was enforced only by a SELECT-then-insert in
confirm, so two concurrent confirms could duplicate a row. Duplicates are merged first,
keeping the cook's word over a machine's, then the most seen, then the most recent -
the same precedence resolution uses.

Revision ID: c8e5a30f172b
Revises: b4d2f7a13c68
Create Date: 2026-09-18 16:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "c8e5a30f172b"
down_revision: str | Sequence[str] | None = "b4d2f7a13c68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def _dedupe_aliases(connection: Connection) -> None:
    """Keep the best alias per (chain, printed name); delete the rest."""
    doomed = (
        connection.execute(
            sa.text(
                """
            SELECT id FROM (
                SELECT id,
                       store_chain,
                       receipt_name,
                       row_number() OVER (
                           PARTITION BY store_chain, receipt_name
                           ORDER BY manually_verified DESC,
                                    occurrence_count DESC,
                                    last_seen DESC,
                                    id
                       ) AS rank
                FROM store_product_alias
            ) ranked
            WHERE rank > 1
            """
            )
        )
        .scalars()
        .all()
    )

    if not doomed:
        logger.info("store_product_alias has no duplicate (chain, name) pairs")
        return

    connection.execute(
        sa.text("DELETE FROM store_product_alias WHERE id = ANY(:ids)"),
        {"ids": list(doomed)},
    )
    logger.warning(
        "Deleted %d duplicate alias row(s); the best mapping per printed name was kept",
        len(doomed),
    )


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    op.add_column(
        "store_product_alias",
        sa.Column("source", sa.String(), nullable=False, server_default="cook"),
    )
    # `manually_verified` is the only provenance the old rows carry.
    connection.execute(
        sa.text(
            "UPDATE store_product_alias "
            "SET source = CASE WHEN manually_verified THEN 'cook' ELSE 'model' END"
        )
    )

    _dedupe_aliases(connection)
    op.create_unique_constraint(
        "uq_store_product_alias_chain_name",
        "store_product_alias",
        ["store_chain", "receipt_name"],
    )


def downgrade() -> None:
    """Downgrade schema. The deleted duplicates are not restored."""
    op.drop_constraint(
        "uq_store_product_alias_chain_name", "store_product_alias", type_="unique"
    )
    op.drop_column("store_product_alias", "source")
