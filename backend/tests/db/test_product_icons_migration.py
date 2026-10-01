"""Q18: the product icon columns migration upgrades from 9c91d21d50ed and downgrades.

Three nullable columns on `product_master`, no backfill: NULL is "no drawing, show the category
emoji", which is how every existing product already behaves.
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
ICON_COLUMNS = {"icon_svg", "icon_status", "icon_updated_at"}


def _load_migration():
    (path,) = VERSIONS.glob("*_product_icons.py")
    spec = importlib.util.spec_from_file_location("product_icons_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_kitchen_shelf_lives(self) -> None:
        assert _load_migration().down_revision == "9c91d21d50ed"

    def test_history_stays_one_line_through_it(self) -> None:
        # Was "the only head" until Q26's f1a2b3c4d5e6 followed it; that test owns the head now.
        script = _script()
        (head,) = script.get_heads()
        ancestors = {rev.revision for rev in script.walk_revisions("base", head)}
        assert _load_migration().revision in ancestors


def _run(sync_conn, step: str) -> None:
    context = MigrationContext.configure(sync_conn)
    with Operations.context(context):
        getattr(_load_migration(), step)()


def _columns(sync_conn) -> dict[str, dict]:
    return {
        c["name"]: c
        for c in inspect(sync_conn).get_columns("product_master")
        if c["name"] in ICON_COLUMNS
    }


class TestTheSchemaChange:
    async def test_downgrade_drops_and_upgrade_recreates(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        built_from_models = await conn.run_sync(_columns)
        assert set(built_from_models) == ICON_COLUMNS

        await conn.run_sync(_run, "downgrade")
        assert await conn.run_sync(_columns) == {}

        await conn.run_sync(_run, "upgrade")
        migrated = await conn.run_sync(_columns)

        assert set(migrated) == ICON_COLUMNS
        assert all(c["nullable"] for c in migrated.values())
        for name in ICON_COLUMNS:
            assert str(migrated[name]["type"]) == str(built_from_models[name]["type"])
