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
image as they did for a drawing.

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


def downgrade() -> None:
    """Downgrade schema. Restores an empty `icon_svg` column - not the rejected drawings."""
    op.drop_column("product_master", "icon_seed")
    op.drop_column("product_master", "icon_image")
    op.add_column("product_master", sa.Column("icon_svg", sa.Text(), nullable=True))
