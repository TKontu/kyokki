"""Q19: produce and fruit placeholders that match the kitchen.

A category's shelf life is only the fallback a new product starts with until its own estimate
lands, but at 7 days a bag of tomatoes or oranges went red in the fridge view within the week.
The operator ruled on 2026-09-26 that produce and fruit keep far longer; meat (5, packed) and
fish (3) were already right. The seed is insert-only, so a deployed database keeps the old
numbers until this migration moves them, and it moves a row only while it still holds the old
value: a number the operator set is theirs. Products are not touched here - re-estimating them
is what "Re-estimate all" is for.
"""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import SEED_CATEGORIES, seed_categories
from app.models.category import Category
from app.models.product_master import ProductMaster

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "9c91d21d50ed_kitchen_shelf_lives.py"
)

CHANGED = {
    "produce": (7, 10),
    "fruits": (7, 10),
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("kitchen_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _days(db: AsyncSession, category_id: str) -> int:
    category = await db.get(Category, category_id, populate_existing=True)
    assert category is not None
    return int(category.default_shelf_life_days)


@pytest.fixture
async def deployed(db_session: AsyncSession) -> AsyncSession:
    """A database seeded before Q19: the old numbers in every changed row."""
    await seed_categories(db_session)
    await db_session.commit()
    for category_id, (old, _) in CHANGED.items():
        category = await db_session.get(Category, category_id)
        category.default_shelf_life_days = old  # type: ignore[union-attr]
    await db_session.commit()
    return db_session


class TestTheSeed:
    def test_new_databases_start_with_the_new_numbers(self) -> None:
        seeded = {c["id"]: c["default_shelf_life_days"] for c in SEED_CATEGORIES}

        assert {k: seeded[k] for k in CHANGED} == {k: v[1] for k, v in CHANGED.items()}

    def test_meat_and_fish_were_already_right(self) -> None:
        seeded = {c["id"]: c["default_shelf_life_days"] for c in SEED_CATEGORIES}

        assert (seeded["meat"], seeded["fish"]) == (5, 3)

    def test_the_migration_and_the_seed_agree(self) -> None:
        migration = _load_migration()

        assert migration.CHANGES == CHANGED

    def test_it_follows_the_current_head(self) -> None:
        assert _load_migration().down_revision == "b7d3e9a4c152"

    def test_it_is_the_only_head(self) -> None:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config()
        config.set_main_option("script_location", str(MIGRATION.parents[1]))

        assert ScriptDirectory.from_config(config).get_heads() == [
            _load_migration().revision
        ]


class TestTheMigration:
    async def test_a_row_still_at_the_old_number_moves(self, deployed) -> None:
        conn = await deployed.connection()

        await conn.run_sync(_load_migration().revise)
        await deployed.commit()

        for category_id, (_, new) in CHANGED.items():
            assert await _days(deployed, category_id) == new

    async def test_a_number_the_operator_set_is_left_alone(self, deployed) -> None:
        produce = await deployed.get(Category, "produce")
        produce.default_shelf_life_days = 12  # type: ignore[union-attr]
        await deployed.commit()
        conn = await deployed.connection()

        await conn.run_sync(_load_migration().revise)
        await deployed.commit()

        assert await _days(deployed, "produce") == 12
        assert await _days(deployed, "fruits") == 10

    async def test_other_categories_do_not_move(self, deployed) -> None:
        before = {c["id"]: await _days(deployed, c["id"]) for c in SEED_CATEGORIES}
        conn = await deployed.connection()

        await conn.run_sync(_load_migration().revise)
        await deployed.commit()

        for category_id, days in before.items():
            if category_id not in CHANGED:
                assert await _days(deployed, category_id) == days

    async def test_products_keep_theirs(self, deployed) -> None:
        tomato = ProductMaster(
            id=uuid4(),
            canonical_name="Tomato",
            category="produce",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            shelf_life_source="category",
            unit_type="count",
            default_unit="pcs",
        )
        deployed.add(tomato)
        await deployed.commit()
        conn = await deployed.connection()

        await conn.run_sync(_load_migration().revise)
        await deployed.commit()

        await deployed.refresh(tomato)
        assert tomato.default_shelf_life_days == 7

    async def test_downgrade_puts_back_only_what_it_moved(self, deployed) -> None:
        migration = _load_migration()
        conn = await deployed.connection()
        await conn.run_sync(migration.revise)
        await deployed.commit()
        fruits = await deployed.get(Category, "fruits")
        fruits.default_shelf_life_days = 14  # type: ignore[union-attr]
        await deployed.commit()
        conn = await deployed.connection()

        await conn.run_sync(migration.restore)
        await deployed.commit()

        assert await _days(deployed, "produce") == 7
        assert await _days(deployed, "fruits") == 14
