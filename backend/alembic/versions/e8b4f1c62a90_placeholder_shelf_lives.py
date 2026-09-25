"""Category placeholders that are not wrong (H57, Q15)

Every new product starts with its category's shelf life until the cook or the catalog
estimate gives it one of its own, and some of those placeholders were absurd: tea, coffee
and juice expired after 30 days, carrots and potatoes after 5. The operator chose these
numbers on 2026-09-25 - err slightly short for perishables, stop being absurd for the rest.

`seed_categories` only inserts missing rows, so a deployed database keeps the old numbers
until this runs. A row moves only while it still holds the old seed value: a number the
operator set by hand is theirs. Products keep their own numbers; replacing a product's
placeholder is what the catalog estimate (H56) is for.

Revision ID: e8b4f1c62a90
Revises: c2d9e4a17b35
Create Date: 2026-09-25 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "e8b4f1c62a90"
down_revision: str | Sequence[str] | None = "c2d9e4a17b35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: category id -> (old seed value, new seed value)
CHANGES: dict[str, tuple[int, int]] = {
    "produce": (5, 7),
    "dairy": (7, 10),
    "beverages": (30, 180),
    "snacks": (60, 90),
}

_MOVE = sa.text(
    "UPDATE category SET default_shelf_life_days = :to "
    "WHERE id = :id AND default_shelf_life_days = :from"
)


def revise(conn: Connection) -> None:
    """Move each category still at its old seed value to the new one."""
    for category_id, (old, new) in CHANGES.items():
        conn.execute(_MOVE, {"id": category_id, "from": old, "to": new})


def restore(conn: Connection) -> None:
    """Put back each category this moved and nobody has edited since."""
    for category_id, (old, new) in CHANGES.items():
        conn.execute(_MOVE, {"id": category_id, "from": new, "to": old})


def upgrade() -> None:
    """Upgrade data."""
    revise(op.get_bind())


def downgrade() -> None:
    """Downgrade data."""
    restore(op.get_bind())
