"""Where a stored shelf life came from (Q11)

`product_master.default_shelf_life_days` is NOT NULL, so creating a product has to put
*something* in it. When no estimate arrived it takes the category's blanket figure, and
from that moment the column cannot tell the three cases apart:

    category  nobody knew, so the category's number stands in. A placeholder.
    model     the model estimated it for this product.
    cook      the cook typed it in the product editor. A correction.

That is why `_fill_gaps` never had a shelf-life branch: with no way to ask "is this a
real answer?", the only safe rule was to write it once at creation and never again. The
cost, measured on the homelab on 2026-09-19: 46 of 50 products carried their category's
blanket figure, all six meat products read 5 days, and `Rye crispbread` sat at 5 while
the model's own 720 lay unused in a stored receipt.

Backfilled by comparing each product against its category, which is the only signal the
old rows carry: equal means the fallback almost certainly fired, different means someone
or something chose that number.

**The comparison is a heuristic and this docstring would rather say so than imply
precision.** A model estimate that happens to equal its category's figure backfills as
`category` and becomes overwritable - three of the twelve seeded categories are 5 days,
so this will happen. The harm is one re-estimate of a value that was already right. The
error runs in the safe direction: no correction is ever mislabelled, because a cook who
opened the editor at all almost certainly changed the number.

Revision ID: f2c91b45d8a7
Revises: d1a7f4b62e93
Create Date: 2026-09-19 14:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c91b45d8a7"
down_revision: str | Sequence[str] | None = "d1a7f4b62e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "product_master",
        sa.Column(
            "shelf_life_source",
            sa.String(),
            nullable=False,
            server_default="category",
        ),
    )

    connection = op.get_bind()
    marked = connection.execute(
        sa.text(
            """
            UPDATE product_master AS p
               SET shelf_life_source = 'model'
              FROM category AS c
             WHERE p.category = c.id
               AND p.default_shelf_life_days IS DISTINCT FROM c.default_shelf_life_days
            """
        )
    ).rowcount
    logger.info(
        "shelf_life_source: %s products differ from their category and read as 'model'; "
        "the rest keep the 'category' default",
        marked,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("product_master", "shelf_life_source")
