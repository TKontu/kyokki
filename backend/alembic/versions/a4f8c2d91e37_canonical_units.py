"""Convert stored quantities to the canonical units dl | tsp | tbsp | g | pcs (MVP-U1)

Data-only migration. Barcode scanning and older clients stored ``ml`` (and receipt confirms
could store ``l``, ``kg`` or ``unit``); the operator ruling DEC-1 makes the canonical units
``dl | tsp | tbsp | g | pcs``. Amounts are scaled with the unit and rounded to two decimals.

The mapping is copied here on purpose: later edits to ``app/services/units.py`` must not change
what this revision did. Rows with units outside the mapping are left untouched and reported.

Downgrade is lossy: ``dl`` goes back to ``ml``; ``g`` and ``pcs`` stay, because rows that were
``kg`` or ``unit`` cannot be told apart from rows that were already ``g`` or ``pcs``.

Revision ID: a4f8c2d91e37
Revises: 7c1f2a9d4b30
Create Date: 2026-09-14 12:00:00.000000

"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "a4f8c2d91e37"
down_revision: str | Sequence[str] | None = "7c1f2a9d4b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# unit (lower-case) -> (factor, canonical unit)
UNIT_MAP: dict[str, tuple[str, str]] = {
    "ml": ("0.01", "dl"),
    "cl": ("0.1", "dl"),
    "l": ("10", "dl"),
    "dl": ("1", "dl"),
    "kg": ("1000", "g"),
    "g": ("1", "g"),
    "unit": ("1", "pcs"),
    "kpl": ("1", "pcs"),
    "st": ("1", "pcs"),
    "pcs": ("1", "pcs"),
    "tsp": ("1", "tsp"),
    "tbsp": ("1", "tbsp"),
}

_MAP_CTE = "unit_map(unit, factor, canonical) AS (VALUES {rows})".format(
    rows=", ".join(
        f"('{unit}', CAST('{factor}' AS NUMERIC), '{canonical}')"
        for unit, (factor, canonical) in UNIT_MAP.items()
    )
)

_KNOWN = ", ".join(f"'{unit}'" for unit in UNIT_MAP)


def convert_units(bind: Connection) -> dict[str, int]:
    """Scale amounts and rewrite units to canonical; returns unknown-unit row counts per table."""
    statements = [
        # 1. Consumption log first: it has no unit column and follows its inventory item's unit.
        f"""
        WITH {_MAP_CTE}
        UPDATE consumption_log AS cl
        SET quantity_consumed = ROUND(cl.quantity_consumed * m.factor, 2)
        FROM inventory_item AS ii
        JOIN unit_map AS m ON lower(trim(ii.unit)) = m.unit
        WHERE cl.inventory_item_id = ii.id AND m.factor <> 1
        """,
        # 2. Inventory items
        f"""
        WITH {_MAP_CTE}
        UPDATE inventory_item AS ii
        SET initial_quantity = ROUND(ii.initial_quantity * m.factor, 2),
            current_quantity = ROUND(ii.current_quantity * m.factor, 2),
            unit = m.canonical
        FROM unit_map AS m
        WHERE lower(trim(ii.unit)) = m.unit AND ii.unit <> m.canonical
        """,
        # 3. Products: amounts, unit, and a unit_type consistent with the unit
        f"""
        WITH {_MAP_CTE}
        UPDATE product_master AS pm
        SET default_quantity = ROUND(pm.default_quantity * m.factor, 2),
            min_stock_quantity = ROUND(pm.min_stock_quantity * m.factor, 2),
            reorder_quantity = ROUND(pm.reorder_quantity * m.factor, 2),
            default_unit = m.canonical
        FROM unit_map AS m
        WHERE lower(trim(pm.default_unit)) = m.unit AND pm.default_unit <> m.canonical
        """,
        """
        UPDATE product_master
        SET unit_type = CASE default_unit
            WHEN 'g' THEN 'weight'
            WHEN 'pcs' THEN 'count'
            ELSE 'volume'
        END
        WHERE default_unit IN ('dl', 'tsp', 'tbsp', 'g', 'pcs')
        """,
        # 4. Shopping list
        f"""
        WITH {_MAP_CTE}
        UPDATE shopping_list_item AS sli
        SET quantity = ROUND(sli.quantity * m.factor, 2),
            unit = m.canonical
        FROM unit_map AS m
        WHERE lower(trim(sli.unit)) = m.unit AND sli.unit <> m.canonical
        """,
    ]
    for statement in statements:
        bind.execute(sa.text(statement))

    unknown = {}
    for table, column in (
        ("inventory_item", "unit"),
        ("product_master", "default_unit"),
        ("shopping_list_item", "unit"),
    ):
        count = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table} WHERE lower(trim({column})) NOT IN ({_KNOWN})"
            )
        ).scalar_one()
        unknown[table] = int(count)
    return unknown


def revert_units(bind: Connection) -> None:
    """Lossy reverse: dl back to ml (x100). g, pcs, tsp and tbsp are left as they are."""
    for statement in (
        """
        UPDATE consumption_log AS cl
        SET quantity_consumed = ROUND(cl.quantity_consumed * 100, 2)
        FROM inventory_item AS ii
        WHERE cl.inventory_item_id = ii.id AND ii.unit = 'dl'
        """,
        """
        UPDATE inventory_item
        SET initial_quantity = ROUND(initial_quantity * 100, 2),
            current_quantity = ROUND(current_quantity * 100, 2),
            unit = 'ml'
        WHERE unit = 'dl'
        """,
        """
        UPDATE product_master
        SET default_quantity = ROUND(default_quantity * 100, 2),
            min_stock_quantity = ROUND(min_stock_quantity * 100, 2),
            reorder_quantity = ROUND(reorder_quantity * 100, 2),
            default_unit = 'ml'
        WHERE default_unit = 'dl'
        """,
        """
        UPDATE shopping_list_item
        SET quantity = ROUND(quantity * 100, 2), unit = 'ml'
        WHERE unit = 'dl'
        """,
    ):
        bind.execute(sa.text(statement))


def upgrade() -> None:
    """Convert stored quantities to canonical units."""
    unknown = convert_units(op.get_bind())
    for table, count in unknown.items():
        if count:
            logger.warning(
                "%s: %d row(s) have a unit outside the canonical mapping and were left as is",
                table,
                count,
            )


def downgrade() -> None:
    """Lossy: dl back to ml only."""
    revert_units(op.get_bind())
