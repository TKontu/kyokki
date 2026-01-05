"""Tests for Category model."""
import pytest
from sqlalchemy import select

from app.models.category import Category


@pytest.mark.asyncio
class TestCategoryModel:
    """Test suite for Category model CRUD operations."""

    async def test_create_category(self, db_session):
        """Test creating a new category."""
        category = Category(
            id="dairy",
            display_name="Dairy Products",
            icon="🥛",
            default_shelf_life_days=7,
            meal_contexts=["breakfast", "cooking"],
            sort_order=1,
        )

        db_session.add(category)
        await db_session.commit()
        await db_session.refresh(category)

        assert category.id == "dairy"
        assert category.display_name == "Dairy Products"
        assert category.icon == "🥛"
        assert category.default_shelf_life_days == 7
        assert category.meal_contexts == ["breakfast", "cooking"]
        assert category.sort_order == 1

    async def test_read_category(self, db_session):
        """Test reading a category from database."""
        # Create category
        category = Category(
            id="meat",
            display_name="Meat & Fish",
            icon="🥩",
            default_shelf_life_days=5,
            meal_contexts=["lunch", "dinner"],
            sort_order=2,
        )
        db_session.add(category)
        await db_session.commit()

        # Read category
        result = await db_session.execute(select(Category).filter(Category.id == "meat"))
        fetched_category = result.scalars().first()

        assert fetched_category is not None
        assert fetched_category.id == "meat"
        assert fetched_category.display_name == "Meat & Fish"
        assert fetched_category.default_shelf_life_days == 5

    async def test_update_category(self, db_session):
        """Test updating a category."""
        # Create category
        category = Category(
            id="produce",
            display_name="Produce",
            icon="🥕",
            default_shelf_life_days=5,
            sort_order=3,
        )
        db_session.add(category)
        await db_session.commit()

        # Update category
        category.default_shelf_life_days = 7
        category.icon = "🥗"
        await db_session.commit()
        await db_session.refresh(category)

        assert category.default_shelf_life_days == 7
        assert category.icon == "🥗"

    async def test_delete_category(self, db_session):
        """Test deleting a category."""
        # Create category
        category = Category(
            id="frozen",
            display_name="Frozen Foods",
            icon="❄️",
            default_shelf_life_days=90,
            sort_order=4,
        )
        db_session.add(category)
        await db_session.commit()

        # Delete category
        await db_session.delete(category)
        await db_session.commit()

        # Verify deletion
        result = await db_session.execute(select(Category).filter(Category.id == "frozen"))
        fetched_category = result.scalars().first()

        assert fetched_category is None

    async def test_list_categories(self, db_session):
        """Test listing all categories."""
        # Create multiple categories
        categories = [
            Category(
                id="dairy",
                display_name="Dairy",
                default_shelf_life_days=7,
                sort_order=1,
            ),
            Category(
                id="meat",
                display_name="Meat",
                default_shelf_life_days=5,
                sort_order=2,
            ),
            Category(
                id="produce",
                display_name="Produce",
                default_shelf_life_days=5,
                sort_order=3,
            ),
        ]

        for category in categories:
            db_session.add(category)
        await db_session.commit()

        # List all categories
        result = await db_session.execute(select(Category).order_by(Category.sort_order))
        all_categories = result.scalars().all()

        assert len(all_categories) == 3
        assert all_categories[0].id == "dairy"
        assert all_categories[1].id == "meat"
        assert all_categories[2].id == "produce"
