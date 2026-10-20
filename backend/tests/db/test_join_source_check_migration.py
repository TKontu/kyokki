"""CL8 L1: a CHECK keeps `inventory_item.join_source` to the known vocabulary."""

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.services.product_identity import JOIN_SOURCES

BACKEND = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND / "alembic" / "versions"


def _load_migration():
    (path,) = VERSIONS.glob("*_join_source_check.py")
    spec = importlib.util.spec_from_file_location("join_source_check_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _script() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


class TestTheRevision:
    def test_it_follows_the_product_reassignment(self) -> None:
        assert _load_migration().down_revision == "e2a9c4f71b38"

    def test_it_is_the_only_head(self) -> None:
        (head,) = _script().get_heads()
        assert head == _load_migration().revision

    def test_its_vocabulary_is_the_services(self) -> None:
        assert tuple(_load_migration().JOIN_SOURCES) == tuple(JOIN_SOURCES)


def _run(sync_conn, step: str) -> None:
    context = MigrationContext.configure(sync_conn)
    with Operations.context(context):
        getattr(_load_migration(), step)()


def _checks(sync_conn) -> set[str]:
    return {
        c["name"] for c in inspect(sync_conn).get_check_constraints("inventory_item")
    }


async def _product(db: AsyncSession) -> ProductMaster:
    await seed_categories(db)
    product = ProductMaster(
        canonical_name="Karelian pie",
        category="ready_meals",
        storage_type="refrigerator",
        default_shelf_life_days=3,
        unit_type="count",
        default_unit="pcs",
        default_quantity=Decimal("1"),
    )
    db.add(product)
    await db.flush()
    return product


async def _insert(db: AsyncSession, product: ProductMaster, source: str | None):
    """Add an item with this join_source inside a savepoint; raises on refusal."""
    async with db.begin_nested():
        db.add(
            InventoryItem(
                product_master_id=product.id,
                initial_quantity=Decimal("1"),
                current_quantity=Decimal("1"),
                unit="pcs",
                status="sealed",
                expiry_date=date(2026, 10, 30),
                location="main_fridge",
                join_source=source,
                join_key="karjalanpaisti",
            )
        )
        await db.flush()


class TestTheConstraint:
    async def test_upgrade_refuses_an_unknown_source_and_downgrade_lifts_it(
        self, db_session: AsyncSession
    ) -> None:
        product = await _product(db_session)
        conn = await db_session.connection()

        await conn.run_sync(_run, "upgrade")
        assert "ck_inventory_item_join_source" in await conn.run_sync(_checks)

        for source in (*JOIN_SOURCES, None):
            await _insert(db_session, product, source)
        with pytest.raises(IntegrityError):
            await _insert(db_session, product, "fuzzy")

        await conn.run_sync(_run, "downgrade")
        assert "ck_inventory_item_join_source" not in await conn.run_sync(_checks)
        await _insert(db_session, product, "fuzzy")
