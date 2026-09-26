"""AG2: the `idempotency_key` table migration upgrades from e8b4f1c62a90 and downgrades."""

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


def _migration_path() -> Path:
    (path,) = VERSIONS.glob("*_idempotency_keys.py")
    return path


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "idempotency_keys_migration", _migration_path()
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_placeholder_shelf_lives(self) -> None:
        assert _load_migration().down_revision == "e8b4f1c62a90"

    def test_it_is_the_only_head(self) -> None:
        assert _script().get_heads() == [_load_migration().revision]


def _run(sync_conn, step: str) -> None:
    context = MigrationContext.configure(sync_conn)
    with Operations.context(context):
        getattr(_load_migration(), step)()


def _shape(sync_conn) -> dict:
    inspector = inspect(sync_conn)
    if "idempotency_key" not in inspector.get_table_names():
        return {}
    return {
        "columns": {c["name"] for c in inspector.get_columns("idempotency_key")},
        "unique": {
            tuple(u["column_names"])
            for u in inspector.get_unique_constraints("idempotency_key")
        },
    }


class TestTheSchemaChange:
    async def test_downgrade_drops_and_upgrade_recreates(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        built_from_models = await conn.run_sync(_shape)

        await conn.run_sync(_run, "downgrade")
        assert await conn.run_sync(_shape) == {}

        await conn.run_sync(_run, "upgrade")
        migrated = await conn.run_sync(_shape)

        assert migrated == built_from_models
        assert migrated["columns"] >= {
            "key",
            "route",
            "request_hash",
            "status_code",
            "response",
            "created_at",
        }
        assert ("key", "route") in migrated["unique"]
