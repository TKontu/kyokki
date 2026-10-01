"""Q18-G2: generated icons replace the rejected SVG drawer's storage.

The migration drops `icon_svg` (the operator's rejected drawings, 2026-09-27) and adds
`icon_image` (the stored PNG) and `icon_seed` (the seed that produced it). `icon_status` and
`icon_updated_at` are untouched - reused from Q18, same four states and same cache-busting
timestamp.

Downgrading restores an empty `icon_svg` column, not the rejected drawings: there is nothing
left to restore them from, and the migration says so in its own docstring.
"""

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
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

    def test_it_is_the_only_head(self) -> None:
        script = _script()
        (head,) = script.get_heads()
        assert head == _load_migration().revision

    def test_history_stays_one_line_through_it(self) -> None:
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
