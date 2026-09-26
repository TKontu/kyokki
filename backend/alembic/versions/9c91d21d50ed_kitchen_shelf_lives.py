"""Produce and fruit placeholders that match the kitchen (Q19)

The fridge view on the iPad showed most of a fresh shop going stale within days, and the
category placeholders were part of why: produce and fruit started every new product at 7
days, while tomatoes and oranges keep far longer. The operator ruled on 2026-09-26 that shelf
life is per product and the category figure is only a fallback; this makes the fallback less
wrong for the two categories it was furthest off in. Meat (5, packed) and fish (3) already
match the ruling.

`seed_categories` only inserts missing rows, so a deployed database keeps the old numbers
until this runs. A row moves only while it still holds the old seed value: a number the
operator set by hand is theirs. Products keep their own numbers; re-estimating them is what
"Re-estimate all" on the products page is for.

Revision ID: 9c91d21d50ed
Revises: b7d3e9a4c152
Create Date: 2026-09-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "9c91d21d50ed"
down_revision: str | Sequence[str] | None = "b7d3e9a4c152"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: category id -> (old seed value, new seed value)
CHANGES: dict[str, tuple[int, int]] = {
    "produce": (7, 10),
    "fruits": (7, 10),
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
