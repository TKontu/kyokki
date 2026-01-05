"""Tests for category seed data script."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.db.seed_categories import SEED_CATEGORIES, seed_categories


class TestSeedCategories:
    """Test category seeding functionality."""

    async def test_seed_categories_data_structure(self) -> None:
        """SEED_CATEGORIES should have expected structure."""
        assert len(SEED_CATEGORIES) > 0, "Should have at least one category"

        for cat in SEED_CATEGORIES:
            assert "id" in cat
            assert "display_name" in cat
            assert "default_shelf_life_days" in cat
            assert isinstance(cat["id"], str)
            assert isinstance(cat["display_name"], str)
            assert isinstance(cat["default_shelf_life_days"], int)
            assert cat["default_shelf_life_days"] > 0

    async def test_seed_categories_creates_categories(
        self, db_session: AsyncSession
    ) -> None:
        """seed_categories should insert all categories into database."""
        # Verify database is empty
        result = await db_session.execute(select(Category))
        assert result.scalars().all() == []

        # Seed the database
        await seed_categories(db_session)
        await db_session.commit()

        # Verify categories were created
        result = await db_session.execute(select(Category))
        categories = result.scalars().all()
        assert len(categories) == len(SEED_CATEGORIES)

    async def test_seed_categories_is_idempotent(
        self, db_session: AsyncSession
    ) -> None:
        """seed_categories should be safe to run multiple times."""
        # Seed once
        await seed_categories(db_session)
        await db_session.commit()

        result = await db_session.execute(select(Category))
        count_first = len(result.scalars().all())

        # Seed again
        await seed_categories(db_session)
        await db_session.commit()

        result = await db_session.execute(select(Category))
        count_second = len(result.scalars().all())

        # Should have same number of categories
        assert count_first == count_second

    async def test_seed_categories_preserves_updates(
        self, db_session: AsyncSession
    ) -> None:
        """seed_categories should not overwrite manual updates."""
        # Seed the database
        await seed_categories(db_session)
        await db_session.commit()

        # Manually update a category
        result = await db_session.execute(select(Category).where(Category.id == "meat"))
        category = result.scalar_one()
        original_shelf_life = category.default_shelf_life_days
        category.default_shelf_life_days = 999
        await db_session.commit()

        # Seed again
        await seed_categories(db_session)
        await db_session.commit()

        # Verify manual update was preserved (not overwritten)
        result = await db_session.execute(select(Category).where(Category.id == "meat"))
        category = result.scalar_one()
        assert category.default_shelf_life_days == 999, "Manual updates should not be overwritten"

    async def test_seed_categories_common_categories_exist(
        self, db_session: AsyncSession
    ) -> None:
        """seed_categories should include common food categories."""
        await seed_categories(db_session)
        await db_session.commit()

        # Check for expected common categories
        expected_ids = ["meat", "dairy", "produce", "frozen", "pantry"]

        for cat_id in expected_ids:
            result = await db_session.execute(
                select(Category).where(Category.id == cat_id)
            )
            category = result.scalar_one_or_none()
            assert category is not None, f"Category '{cat_id}' should exist in seed data"
            assert category.display_name, f"Category '{cat_id}' should have display_name"
