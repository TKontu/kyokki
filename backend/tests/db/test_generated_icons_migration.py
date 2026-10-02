"""Q18-G2: generated icons replace the rejected SVG drawer's storage.

The migration drops `icon_svg` (the operator's rejected drawings, 2026-09-27) and adds
`icon_image` (the stored PNG) and `icon_seed` (the seed that produced it). `icon_status` and
`icon_updated_at` are untouched - reused from Q18, same four states and same cache-busting
timestamp.

Downgrading restores an empty `icon_svg` column, not the rejected drawings: there is nothing
left to restore them from, and the migration says so in its own docstring.
"""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"
NEW_COLUMNS = {"icon_image", "icon_seed"}
UNCHANGED_COLUMNS = {"icon_status", "icon_updated_at"}


def _load_migration():
    (path,) = VERSIONS.glob("*_generated_product_icons.py")
    spec = importlib.util.spec_from_file_location("generated_icons_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_exact_emoji_gap_list(self) -> None:
        assert _load_migration().down_revision == "fbf2c08da52d"

    def test_history_stays_one_line_through_it(self) -> None:
        # Was "the only head" until Post-MVP frontier item 13's 61f6f69cc22f followed it;
        # that test owns the head now (tests/db/test_display_names_migration.py).
        script = _script()
        (head,) = script.get_heads()
        ancestors = {rev.revision for rev in script.walk_revisions("base", head)}
        assert _load_migration().revision in ancestors


def _run(sync_conn, step: str) -> None:
    context = MigrationContext.configure(sync_conn)
    with Operations.context(context):
        getattr(_load_migration(), step)()


def _columns(sync_conn) -> dict[str, dict]:
    return {c["name"]: c for c in inspect(sync_conn).get_columns("product_master")}


class TestTheSchemaChange:
    async def test_downgrade_restores_an_empty_icon_svg_not_the_drawings(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        built_from_models = await conn.run_sync(_columns)
        # The rejected SVG drawer's column is gone from the live model (dropped here).
        assert "icon_svg" not in built_from_models
        assert set(built_from_models) >= NEW_COLUMNS
        assert set(built_from_models) >= UNCHANGED_COLUMNS

        await conn.run_sync(_run, "downgrade")
        downgraded = await conn.run_sync(_columns)
        assert not (NEW_COLUMNS & set(downgraded))
        assert "icon_svg" in downgraded
        assert downgraded["icon_svg"]["nullable"] is True
        assert str(downgraded["icon_svg"]["type"]).upper().startswith("TEXT")
        # The column is back, but empty: nothing here or in the migration recovers the
        # rejected drawings it once held.
        assert set(downgraded) >= UNCHANGED_COLUMNS

        await conn.run_sync(_run, "upgrade")
        reupgraded = await conn.run_sync(_columns)
        assert "icon_svg" not in reupgraded
        assert set(reupgraded) >= NEW_COLUMNS
        for name in NEW_COLUMNS:
            assert reupgraded[name]["nullable"] is True
            assert str(reupgraded[name]["type"]) == str(built_from_models[name]["type"])

    async def test_icon_image_and_seed_have_the_right_types(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        columns = await conn.run_sync(_columns)

        assert str(columns["icon_image"]["type"]).upper() in ("BYTEA", "LARGEBINARY")
        assert str(columns["icon_seed"]["type"]).upper() in ("BIGINT", "INTEGER")


class TestOrphanedRowsBackfill:
    """F1: a row the old SVG drawer finished (`ready`) or had mid-flight (`pending`) carries
    that status straight through the `icon_svg` -> `icon_image` swap, but `icon_image` starts
    NULL for everyone. Without the backfill, such a row would claim a version
    (`icon_version` is non-null whenever `icon_updated_at` is) with no image behind it: every
    tile would request `icon.png` and get a 404, and the gap queue would never re-pick it up
    (`ready` never counted as needing one). `cleared` is the one status an empty image is
    correct for and must survive untouched.
    """

    async def test_ready_and_pending_are_reset_cleared_is_left_alone(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        await conn.run_sync(
            _run, "downgrade"
        )  # back to icon_svg, no icon_image/icon_seed

        await conn.execute(
            text(
                "INSERT INTO category (id, display_name, default_shelf_life_days, sort_order) "
                "VALUES ('produce-f1', 'Produce', 10, 1) ON CONFLICT (id) DO NOTHING"
            )
        )
        now = datetime.now(UTC)
        rows = {
            "ready": ("<svg><circle/></svg>", "ready", now),
            "pending": (None, "pending", now),
            "cleared": (None, "cleared", None),
            "never": (None, None, None),
        }
        ids = {name: uuid4() for name in rows}
        for name, (svg, status, updated) in rows.items():
            await conn.execute(
                text(
                    "INSERT INTO product_master "
                    "(id, canonical_name, category, storage_type, default_shelf_life_days, "
                    " shelf_life_source, unit_type, default_unit, icon_svg, icon_status, "
                    " icon_updated_at, created_at, updated_at) "
                    "VALUES (:id, :name, 'produce-f1', 'refrigerator', 10, "
                    " 'category', 'count', 'pcs', :svg, :status, :updated, :now, :now)"
                ),
                {
                    "id": ids[name],
                    "name": f"F1 {name} row",
                    "svg": svg,
                    "status": status,
                    "updated": updated,
                    "now": now,
                },
            )

        await conn.run_sync(_run, "upgrade")

        result = await conn.execute(
            text(
                "SELECT id, icon_status, icon_updated_at, icon_seed, icon_image "
                "FROM product_master WHERE id = ANY(:ids)"
            ),
            {"ids": list(ids.values())},
        )
        rows_by_id = {row.id: row for row in result}
        by_name = {name: rows_by_id[row_id] for name, row_id in ids.items()}

        for name in ("ready", "pending", "never"):
            row = by_name[name]
            assert row.icon_status is None, name
            assert row.icon_updated_at is None, name
            assert row.icon_seed is None, name
            assert row.icon_image is None, name

        cleared = by_name["cleared"]
        assert cleared.icon_status == "cleared"
        assert cleared.icon_updated_at is None
        assert cleared.icon_image is None
