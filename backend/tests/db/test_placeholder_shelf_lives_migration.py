"""H57 (Q15): category placeholders that are not wrong.

A category's shelf life is only a placeholder - a product gets its own from the cook or the
catalog estimate - but it is what every new product starts with, and some were absurd: tea
and juice at 30 days, carrots at 5. The seed is insert-only (`ON CONFLICT DO NOTHING`), so a
deployed database keeps the old numbers until a migration moves them. It moves a row only
while it still holds the old seed value: a number the operator set is theirs.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import SEED_CATEGORIES, seed_categories
from app.models.category import Category
from app.models.product_master import ProductMaster

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "e8b4f1c62a90_placeholder_shelf_lives.py"
)

CHANGED = {
    "produce": (5, 7),
    "dairy": (7, 10),
    "beverages": (30, 180),
    "snacks": (60, 90),
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("placeholder_migration", MIGRATION)
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
    """A database seeded before H57: the old numbers in every changed row."""
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

    def test_the_migration_and_the_seed_agree(self) -> None:
        migration = _load_migration()

        assert migration.CHANGES == CHANGED

    def test_nothing_else_moved(self) -> None:
        seeded = {c["id"]: c["default_shelf_life_days"] for c in SEED_CATEGORIES}

        assert {k: v for k, v in seeded.items() if k not in CHANGED} == {
            "meat": 5,
            "fish": 3,
            "cheese": 25,
            "fruits": 7,
            "bread": 5,
            "ready_meals": 4,
            "frozen": 90,
            "pantry": 365,
            "condiments": 180,
        }


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
        assert await _days(deployed, "dairy") == 10

    async def test_products_keep_theirs(self, deployed) -> None:
        """A product's number is its own; H56's estimate is what replaces placeholders."""
        from uuid import uuid4

        carrot = ProductMaster(
            id=uuid4(),
            canonical_name="Carrot",
            category="produce",
            storage_type="refrigerator",
            default_shelf_life_days=5,
            unit_type="count",
            default_unit="pcs",
        )
        deployed.add(carrot)
        await deployed.commit()
        conn = await deployed.connection()

        await conn.run_sync(_load_migration().revise)
        await deployed.commit()

        await deployed.refresh(carrot)
        assert carrot.default_shelf_life_days == 5

    async def test_downgrade_puts_back_only_what_it_moved(self, deployed) -> None:
        migration = _load_migration()
        conn = await deployed.connection()
        await conn.run_sync(migration.revise)
        await deployed.commit()
        dairy = await deployed.get(Category, "dairy")
        dairy.default_shelf_life_days = 14  # type: ignore[union-attr]
        await deployed.commit()
        conn = await deployed.connection()

        await conn.run_sync(migration.restore)
        await deployed.commit()

        assert await _days(deployed, "produce") == 5
        assert await _days(deployed, "dairy") == 14
