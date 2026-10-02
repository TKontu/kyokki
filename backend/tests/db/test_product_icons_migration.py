"""Q18: the product icon columns migration upgrades from 9c91d21d50ed and downgrades.

Three nullable columns on `product_master`, no backfill: NULL is "no drawing, show the category
emoji", which is how every existing product already behaved.

`icon_svg` itself is history now: a later migration (Q18-G2, `test_generated_icons_migration.py`)
drops it for good - the operator rejected every drawing on 2026-09-27 and asked for it cleared,
and there is nothing left to draw it back from. This revision still correctly added it at its
point in history, and still exists unedited; the live-schema round trip below only exercises
`icon_status` and `icon_updated_at`, the two columns of its own that are still standing.
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
ALL_ICON_COLUMNS = {"icon_svg", "icon_status", "icon_updated_at"}
STILL_STANDING = {"icon_status", "icon_updated_at"}


def _load_migration():
    # Not "*_product_icons.py": Q18-G2's own revision file also ends that way
    # ("..._generated_product_icons.py"). This is the original Q18 drawer's revision only.
    (path,) = VERSIONS.glob("e4b8c1d7a236_product_icons.py")
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


def _columns(sync_conn) -> dict[str, dict]:
    return {
        c["name"]: c
        for c in inspect(sync_conn).get_columns("product_master")
        if c["name"] in ALL_ICON_COLUMNS
    }


class TestTheSchemaChange:
    async def test_icon_status_and_icon_updated_at_are_still_standing(
        self, db_session: AsyncSession
    ) -> None:
        """`icon_svg` is gone (Q18-G2 dropped it); the other two columns this revision added
        are reused unchanged, so the live schema still carries exactly those two."""
        conn = await db_session.connection()
        built_from_models = await conn.run_sync(_columns)

        assert set(built_from_models) == STILL_STANDING
        assert all(c["nullable"] for c in built_from_models.values())

    async def test_this_revisions_own_upgrade_and_downgrade_still_add_and_drop_all_three(
        self, db_session: AsyncSession
    ) -> None:
        """This revision's own code, unedited, still adds and drops the three columns it
        always did - `icon_svg` included. The live schema no longer has `icon_svg` (Q18-G2
        dropped it for good, in a later revision this one knows nothing about), so it is put
        back first - exactly the schema state this revision's own ops were written against.
        """
        from sqlalchemy import text

        conn = await db_session.connection()

        def _run(sync_conn, step: str) -> None:
            context = MigrationContext.configure(sync_conn)
            with Operations.context(context):
                getattr(_load_migration(), step)()

        await conn.execute(text("ALTER TABLE product_master ADD COLUMN icon_svg TEXT"))
        assert set(await conn.run_sync(_columns)) == ALL_ICON_COLUMNS

        await conn.run_sync(_run, "downgrade")
        assert await conn.run_sync(_columns) == {}

        await conn.run_sync(_run, "upgrade")
        migrated = await conn.run_sync(_columns)

        assert set(migrated) == ALL_ICON_COLUMNS
        assert all(c["nullable"] for c in migrated.values())
        # `db_session` rolls the whole test back (see its docstring in conftest.py), so the
        # live schema this test started from is restored automatically; nothing to undo here.
