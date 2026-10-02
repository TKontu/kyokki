"""Generated product icons replace the rejected SVG drawer (Q18-G2)

The operator rejected the model-drawn SVG icon on 2026-09-27 (docs/spikes/Q18_icon_styles.md)
and asked for it cleared. `icon_svg` is dropped here - **downgrading this migration restores
an empty column, not the drawings**: nothing recovers the rejected SVG markup.

In its place, `services/product_icons.py` (Q18-G2) generates a flat icon through ComfyUI
(`services/comfyui.py`, `services/icon_workflow.py`, #135) for a food product with no exact
emoji, downscales it with Pillow and stores it as a small transparent PNG:

- `icon_image`: the stored PNG, deferred like `icon_svg` was - listing products does not load
  it, only `GET /products/{id}/icon.png` does.
- `icon_seed`: the seed ComfyUI used for the stored image, for Regenerate's "a new one, not
  this one again".

`icon_status` and `icon_updated_at` are reused unchanged: the four status values (pending,
ready, failed, cleared) and the cache-busting timestamp mean the same thing for a generated
image as they did for a drawing. A product the old drawer had finished (`ready`, with an
`icon_updated_at`) or had mid-flight (`pending`) carries that status straight through the
`icon_svg` -> `icon_image` swap, but `icon_image` starts NULL for everyone: without a data
fix, such a row would claim a version (`icon_version` is non-null whenever `icon_updated_at`
is) with nothing behind it, so every tile would request `icon.png` and get a 404, and the
gap queue would never pick it up (`ready` never counts as needing one). `upgrade` resets
`icon_status`/`icon_updated_at`/`icon_seed` back to NULL - "never generated" - for every row
that is not `cleared` and has no image, which after the column add is every row that was not
`cleared` under the old drawer either.

Revision ID: c715f1ea4510
Revises: fbf2c08da52d
Create Date: 2026-10-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c715f1ea4510"
down_revision: str | Sequence[str] | None = "fbf2c08da52d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("product_master", "icon_svg")
    op.add_column(
        "product_master", sa.Column("icon_image", sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        "product_master", sa.Column("icon_seed", sa.BigInteger(), nullable=True)
    )
    # Every row just lost its drawing (icon_image is NULL for all of them, including the ones
    # the old drawer had finished or had mid-flight) - so any status but `cleared` is now a
    # lie about an image that is not there. `cleared` is the one status an empty image is
    # correct for and must survive untouched; everything else goes back to "never generated".
    op.execute(
        """
        UPDATE product_master
        SET icon_status = NULL, icon_updated_at = NULL, icon_seed = NULL
        WHERE icon_image IS NULL AND icon_status IS DISTINCT FROM 'cleared'
        """
    )


def downgrade() -> None:
    """Downgrade schema. Restores an empty `icon_svg` column - not the rejected drawings."""
    op.drop_column("product_master", "icon_seed")
    op.drop_column("product_master", "icon_image")
    op.add_column("product_master", sa.Column("icon_svg", sa.Text(), nullable=True))
