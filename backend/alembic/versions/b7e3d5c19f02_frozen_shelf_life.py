"""How long a category keeps in the freezer (Q12, DEC-10)

Mince frozen on the day it was bought still read expired six days later, because expiry came
from the product's *fridge* shelf life and moving an item to the freezer changed nothing. The
edit sheet has always let a cook move an item there, so the wrong answer was already reachable.

`frozen_shelf_life_days` is nullable on purpose: NULL means freezing does not change the clock
for this kind of thing. Pantry goods, drinks, condiments and snacks get none - nothing useful
happens to a frozen bottle of squash, and inventing a number for it would be worse than saying
nothing.

**The values are seeded, not estimated.** Unlike Q11's shelf lives, no model was asked. They are
deliberately conservative household figures rather than food-safety limits: frozen food keeps
almost indefinitely and these are about quality, which is the thing a cook actually notices.
Every one of them is a number that can be wrong, and the escape hatch is the same as everywhere
else - editing the date by hand marks it `manual` and no recompute touches it again.

`seed_categories` uses `on_conflict_do_nothing`, so it will not fill this in for the twelve
categories that already exist on a running deployment. That is what the UPDATE below is for.

Revision ID: b7e3d5c19f02
Revises: f2c91b45d8a7
Create Date: 2026-09-19 17:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e3d5c19f02"
down_revision: str | Sequence[str] | None = "f2c91b45d8a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Days, by category id. Absent means "freezing this is not a thing we model".
FROZEN_DAYS = {
    "meat": 180,
    "fish": 120,
    "dairy": 90,
    "cheese": 180,
    "produce": 240,
    "fruits": 240,
    "bread": 90,
    "frozen": 365,
}


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "category",
        sa.Column("frozen_shelf_life_days", sa.Integer(), nullable=True),
    )

    connection = op.get_bind()
    filled = 0
    for category_id, days in FROZEN_DAYS.items():
        filled += connection.execute(
            sa.text(
                """
                UPDATE category
                   SET frozen_shelf_life_days = :days
                 WHERE id = :id
                   AND frozen_shelf_life_days IS NULL
                """
            ),
            {"days": days, "id": category_id},
        ).rowcount
    logger.info(
        "frozen_shelf_life_days: filled %s of %s seeded categories; the rest keep NULL, "
        "which means freezing does not change their clock",
        filled,
        len(FROZEN_DAYS),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("category", "frozen_shelf_life_days")
