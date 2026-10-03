"""Post-MVP frontier item 13: the `product_display_name` table.

A new table over a JSONB column on `product_master`: one row per (product, language), with
its own `source` (cook or model) per language rather than one shared per product. Downgrading
drops the table - a cook-typed Finnish name is not recoverable, as the migration's own
docstring says.
"""

import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"


def _load_migration():
    (path,) = VERSIONS.glob("*_product_display_names.py")
    spec = importlib.util.spec_from_file_location("display_names_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_generated_icons(self) -> None:
        assert _load_migration().down_revision == "c715f1ea4510"

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


def _table_names(sync_conn) -> set[str]:
    return set(inspect(sync_conn).get_table_names())


def _columns(sync_conn) -> dict[str, dict]:
    return {
        c["name"]: c for c in inspect(sync_conn).get_columns("product_display_name")
    }


class TestTheSchemaChange:
    async def test_the_table_exists_with_the_right_columns(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        columns = await conn.run_sync(_columns)

        for name in (
            "id",
            "product_master_id",
            "language",
            "name",
            "source",
            "created_at",
            "updated_at",
        ):
            assert name in columns, name
        assert columns["product_master_id"]["nullable"] is False
        assert columns["language"]["nullable"] is False
        assert columns["name"]["nullable"] is False
        assert columns["source"]["nullable"] is False

    async def test_downgrade_drops_the_table_not_just_data(
        self, db_session: AsyncSession
    ) -> None:
        conn = await db_session.connection()
        before = await conn.run_sync(_table_names)
        assert "product_display_name" in before

        await conn.run_sync(_run, "downgrade")
        after_down = await conn.run_sync(_table_names)
        assert "product_display_name" not in after_down

        await conn.run_sync(_run, "upgrade")
        after_up = await conn.run_sync(_table_names)
        assert "product_display_name" in after_up


class TestConstraints:
    async def test_one_row_per_product_and_language(
        self, db_session: AsyncSession
    ) -> None:
        await db_session.execute(
            text(
                "INSERT INTO category (id, display_name, default_shelf_life_days, "
                "sort_order) VALUES ('dairy-dn', 'Dairy', 10, 1) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        product_id = uuid4()
        await db_session.execute(
            text(
                "INSERT INTO product_master "
                "(id, canonical_name, category, storage_type, default_shelf_life_days, "
                " shelf_life_source, unit_type, default_unit, created_at, updated_at) "
                "VALUES (:id, 'Milk DN', 'dairy-dn', 'refrigerator', 10, 'cook', "
                " 'count', 'pcs', now(), now())"
            ),
            {"id": product_id},
        )
        await db_session.execute(
            text(
                "INSERT INTO product_display_name "
                "(id, product_master_id, language, name, source, created_at, updated_at) "
                "VALUES (:id, :product_id, 'fi', 'Maito', 'cook', now(), now())"
            ),
            {"id": uuid4(), "product_id": product_id},
        )
        await db_session.flush()

        try:
            await db_session.execute(
                text(
                    "INSERT INTO product_display_name "
                    "(id, product_master_id, language, name, source, created_at, "
                    " updated_at) "
                    "VALUES (:id, :product_id, 'fi', 'Toinen nimi', 'model', now(), "
                    " now())"
                ),
                {"id": uuid4(), "product_id": product_id},
            )
            await db_session.flush()
        except IntegrityError:
            pass
        else:
            raise AssertionError(
                "a second 'fi' row for the same product should violate the unique "
                "constraint"
            )

    async def test_deleting_the_product_deletes_its_display_names(
        self, db_session: AsyncSession
    ) -> None:
        await db_session.execute(
            text(
                "INSERT INTO category (id, display_name, default_shelf_life_days, "
                "sort_order) VALUES ('dairy-dn2', 'Dairy', 10, 1) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        product_id = uuid4()
        await db_session.execute(
            text(
                "INSERT INTO product_master "
                "(id, canonical_name, category, storage_type, default_shelf_life_days, "
                " shelf_life_source, unit_type, default_unit, created_at, updated_at) "
                "VALUES (:id, 'Milk DN2', 'dairy-dn2', 'refrigerator', 10, 'cook', "
                " 'count', 'pcs', now(), now())"
            ),
            {"id": product_id},
        )
        name_id = uuid4()
        await db_session.execute(
            text(
                "INSERT INTO product_display_name "
                "(id, product_master_id, language, name, source, created_at, updated_at) "
                "VALUES (:id, :product_id, 'fi', 'Maito', 'cook', now(), now())"
            ),
            {"id": name_id, "product_id": product_id},
        )
        await db_session.flush()

        await db_session.execute(
            text("DELETE FROM product_master WHERE id = :id"), {"id": product_id}
        )
        await db_session.flush()

        remaining = (
            await db_session.execute(
                text("SELECT 1 FROM product_display_name WHERE id = :id"),
                {"id": name_id},
            )
        ).first()
        assert remaining is None
