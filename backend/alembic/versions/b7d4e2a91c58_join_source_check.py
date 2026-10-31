"""Only known values in `inventory_item.join_source` (CL8 L1)

The identity lane now fills `join_source` on every item confirm, quick add and the agents'
stock add create (`docs/PRODUCT_IDENTITY_SPEC.md`, "Provenance per join"). A CHECK keeps the
column to the known vocabulary; NULL stays allowed for items created before this lane.

`store_product_alias.source` is free text with no CHECK, so the new `cook_accepted` value
needs no constraint change.

Revision ID: b7d4e2a91c58
Revises: e2a9c4f71b38
Create Date: 2026-10-18 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7d4e2a91c58"
down_revision: str | Sequence[str] | None = "e2a9c4f71b38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_inventory_item_join_source"
# Mirrors `app.services.product_identity.JOIN_SOURCES`; a migration must not import app code.
JOIN_SOURCES = (
    "created",
    "alias",
    "name",
    "cook_pick",
    "accepted_suggestion",
    "quick_add",
    "agent",
    "merge",
    "split",
    "legacy",
)


def upgrade() -> None:
    allowed = ", ".join(f"'{value}'" for value in JOIN_SOURCES)
    op.create_check_constraint(
        CONSTRAINT,
        "inventory_item",
        f"join_source IS NULL OR join_source IN ({allowed})",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "inventory_item", type_="check")
