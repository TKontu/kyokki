"""Trigram search over product names, for candidate shortlists (H13)

`pg_trgm` is the only place similarity survives the H1 refactor, and it no longer
decides anything: it builds a shortlist of at most five candidates that the model
chooses from, and the choice is rejected unless it was on the list
(`docs/PRODUCT_RESOLUTION_SPEC.md` §3.3).

The extension ships with postgres:15 and with the CI service container, which runs as
a superuser. `CREATE EXTENSION` needs that privilege; a locked-down role would fail
here, which is why it is its own revision and not buried in a data migration.

Revision ID: b4d2f7a13c68
Revises: a1c6e2f90b45
Create Date: 2026-09-18 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b4d2f7a13c68"
down_revision: str | Sequence[str] | None = "a1c6e2f90b45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # GIN over the trigrams of every known name, so `similarity()` does not scan the
    # catalog once per unresolved line.
    op.execute(
        "CREATE INDEX ix_product_name_name_trgm "
        "ON product_name USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    """Downgrade schema.

    The extension is left in place: other things may have come to depend on it, and
    dropping it would take their indexes with it.
    """
    op.execute("DROP INDEX IF EXISTS ix_product_name_name_trgm")
