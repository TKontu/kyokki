"""Product names: synonyms as keys, and one product per name (H11)

Three steps, in this order because each depends on the last:

1. **Dedupe `product_master` by `lower(canonical_name)`.** Duplicates are legal today
   (only a non-unique index exists), and the receipt pipeline could create them: two
   spellings of one thing became two products. The oldest row wins; every reference is
   repointed to it and the losers are deleted. What was merged is logged - this is the
   one irreversible step in the wave.
2. **`UNIQUE INDEX ON lower(canonical_name)`**, so no new exact duplicate can appear.
3. **`product_name`**, backfilled with every product's canonical name. From here a name
   is a key: resolution looks names up rather than scoring them
   (`docs/PRODUCT_RESOLUTION_SPEC.md` §3.1).

Downgrade drops the table and the index. It cannot un-merge the duplicates; the log line
from step 1 is the only record, which is why it names every row it touched.

Revision ID: a1c6e2f90b45
Revises: f3b8c1d4e207
Create Date: 2026-09-18 10:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "a1c6e2f90b45"
down_revision: str | Sequence[str] | None = "f3b8c1d4e207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Everything that points at a product and must follow it when duplicates merge.
REFERENCING_TABLES = (
    ("inventory_item", "product_master_id"),
    ("store_product_alias", "product_master_id"),
    ("shopping_list_item", "product_master_id"),
    ("consumption_log", "product_master_id"),
)


def _dedupe_products(connection: Connection) -> None:
    """Point every reference at the oldest product of each name, drop the rest."""
    groups = connection.execute(
        sa.text(
            """
            SELECT lower(btrim(canonical_name)) AS key,
                   array_agg(id ORDER BY created_at, id) AS ids,
                   array_agg(canonical_name ORDER BY created_at, id) AS names
            FROM product_master
            GROUP BY lower(btrim(canonical_name))
            HAVING count(*) > 1
            """
        )
    ).all()

    if not groups:
        logger.info("product_master has no duplicate names; nothing to merge")
        return

    for key, ids, names in groups:
        keeper, losers = ids[0], ids[1:]
        for table, column in REFERENCING_TABLES:
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = :keeper "  # noqa: S608 - fixed names
                    f"WHERE {column} = ANY(:losers)"
                ),
                {"keeper": keeper, "losers": losers},
            )
        connection.execute(
            sa.text("DELETE FROM product_master WHERE id = ANY(:losers)"),
            {"losers": losers},
        )
        logger.warning(
            "Merged duplicate products for %r: kept %s, deleted %s (names: %s)",
            key,
            keeper,
            ", ".join(str(i) for i in losers),
            ", ".join(names),
        )

    logger.warning("Merged %d duplicate product name group(s)", len(groups))


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    _dedupe_products(connection)

    # A functional index, so "Oat milk" and "oat milk" cannot both exist.
    op.create_index(
        "uq_product_master_canonical_name_lower",
        "product_master",
        [sa.text("lower(btrim(canonical_name))")],
        unique=True,
    )

    op.create_table(
        "product_name",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_master_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_master_id"], ["product_master.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_product_name_name"),
    )
    op.create_index(op.f("ix_product_name_id"), "product_name", ["id"])
    op.create_index(op.f("ix_product_name_name"), "product_name", ["name"])
    op.create_index(
        op.f("ix_product_name_product_master_id"), "product_name", ["product_master_id"]
    )

    # Backfill: every product's canonical name is a key from now on. The dedupe above
    # guarantees these are unique, so the UNIQUE (name) constraint cannot trip here.
    inserted = connection.execute(
        sa.text(
            """
            INSERT INTO product_name (id, product_master_id, name, source, created_at)
            SELECT gen_random_uuid(), id, lower(btrim(canonical_name)), 'canonical', now()
            FROM product_master
            """
        )
    ).rowcount
    logger.info("Seeded %s canonical product names", inserted)


def downgrade() -> None:
    """Downgrade schema. The merged duplicates are not restored."""
    op.drop_index(op.f("ix_product_name_product_master_id"), table_name="product_name")
    op.drop_index(op.f("ix_product_name_name"), table_name="product_name")
    op.drop_index(op.f("ix_product_name_id"), table_name="product_name")
    op.drop_table("product_name")
    op.drop_index("uq_product_master_canonical_name_lower", table_name="product_master")
