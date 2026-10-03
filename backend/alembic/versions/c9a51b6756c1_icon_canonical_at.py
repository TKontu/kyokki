"""Mark a generated icon canonical, for curation into the repo's icon library

Operator ruling (2026-10-03): "The generated -> canonical should be a feature of the
'develop' production build I use. ... during use more [icons] are generated and some are
re-generated and after that updated canonical [icons] can be submitted to the repo." On a
develop build with `ICON_CURATION_ENABLED` set, the cook marks a good generated icon on the
product sheet; Settings lists every marked product and downloads them as one bundle
(`GET /api/icon-library/bundle.zip`), which `backend/scripts/apply_icon_bundle.py` merges
into `app/resources/icon_library/` for a PR.

`icon_canonical_at` is nullable timestamptz, NULL meaning "not marked" - the same shape as
`icon_updated_at`. A mark is only ever set on a product whose icon is actually generated
(`icon_seed` not NULL, `icon_status` ready) and not already shown by an emoji
(`services/icon_library.py` enforces this; the column itself carries no constraint, since a
generated image can later be regenerated or cleared without the database needing to know
the eligibility rule). A fresh render (Regenerate, or a rename's automatic one) or a clear
drops the mark in the same write that changes the image - the marked image is gone either
way - so no backfill is needed here: every existing row already has nothing marked.

Revision ID: c9a51b6756c1
Revises: 61f6f69cc22f
Create Date: 2026-10-03 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9a51b6756c1"
down_revision: str | Sequence[str] | None = "61f6f69cc22f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "product_master",
        sa.Column("icon_canonical_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema. Drops the column - a mark is a curation convenience, not data
    the cook typed; nothing recovers it, same as any other icon-state column here."""
    op.drop_column("product_master", "icon_canonical_at")
