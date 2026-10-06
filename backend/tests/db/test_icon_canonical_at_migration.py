"""Icon curation (operator ask 2026-10-03): the `product_master.icon_canonical_at` column.

One nullable timestamptz, no backfill - NULL means "not marked", which is how every
existing product already behaves. Downgrading drops the column: a mark is a curation
convenience, not something the cook typed, so there is nothing to recover.
"""

import importlib.util
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


def _load_migration():
    (path,) = VERSIONS.glob("*_icon_canonical_at.py")
    spec = importlib.util.spec_from_file_location("icon_canonical_at_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_display_names(self) -> None:
        assert _load_migration().down_revision == "61f6f69cc22f"

    # Was "the only head" until CL5's d8f3a61c2b57 followed it (round 2026-10-06-1,
    # `test_telegram_receipt_message_migration.py`); that test owns the head now.

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
    async def test_the_column_exists_and_is_nullable(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        columns = await conn.run_sync(_columns)

        assert "icon_canonical_at" in columns
        assert columns["icon_canonical_at"]["nullable"] is True

    async def test_downgrade_drops_the_column_and_upgrade_restores_it(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()

        await conn.run_sync(_run, "downgrade")
        after_down = await conn.run_sync(_columns)
        assert "icon_canonical_at" not in after_down

        await conn.run_sync(_run, "upgrade")
        after_up = await conn.run_sync(_columns)
        assert "icon_canonical_at" in after_up
        assert after_up["icon_canonical_at"]["nullable"] is True

    async def test_an_existing_product_reads_as_not_marked(
        self, db_session: AsyncSession
    ) -> None:
        """No backfill: every row that existed before this migration simply has NULL,
        which `is_markable`/the API both already read as "not marked"."""
        await db_session.execute(
            text(
                "INSERT INTO category (id, display_name, default_shelf_life_days, "
                "sort_order) VALUES ('dairy-ic', 'Dairy', 10, 1) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        product_id = uuid4()
        await db_session.execute(
            text(
                "INSERT INTO product_master "
                "(id, canonical_name, category, storage_type, default_shelf_life_days, "
                " shelf_life_source, unit_type, default_unit, created_at, updated_at) "
                "VALUES (:id, 'Milk IC', 'dairy-ic', 'refrigerator', 10, 'cook', "
                " 'count', 'pcs', now(), now())"
            ),
            {"id": product_id},
        )
        await db_session.flush()

        row = (
            await db_session.execute(
                text("SELECT icon_canonical_at FROM product_master WHERE id = :id"),
                {"id": product_id},
            )
        ).first()

        assert row is not None
        assert row[0] is None
