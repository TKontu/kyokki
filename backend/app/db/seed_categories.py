"""Seed data for product categories."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


# Seed data based on common food categories and their typical shelf lives
SEED_CATEGORIES = [
    {
        "id": "meat",
        "display_name": "Meat & Poultry",
        "icon": "🥩",
        "default_shelf_life_days": 5,
        "meal_contexts": ["cooking", "grilling"],
        "sort_order": 10,
    },
    {
        "id": "fish",
        "display_name": "Fish & Seafood",
        "icon": "🐟",
        "default_shelf_life_days": 3,
        "meal_contexts": ["cooking"],
        "sort_order": 20,
    },
    {
        "id": "dairy",
        "display_name": "Dairy & Eggs",
        "icon": "🥛",
        "default_shelf_life_days": 7,
        "meal_contexts": ["breakfast", "cooking", "baking"],
        "sort_order": 30,
    },
    {
        "id": "cheese",
        "display_name": "Cheese",
        "icon": "🧀",
        "default_shelf_life_days": 25,
        "meal_contexts": ["snack", "cooking"],
        "sort_order": 40,
    },
    {
        "id": "produce",
        "display_name": "Fresh Produce",
        "icon": "🥬",
        "default_shelf_life_days": 5,
        "meal_contexts": ["cooking", "salad", "snack"],
        "sort_order": 50,
    },
    {
        "id": "fruits",
        "display_name": "Fruits",
        "icon": "🍎",
        "default_shelf_life_days": 7,
        "meal_contexts": ["breakfast", "snack", "dessert"],
        "sort_order": 60,
    },
    {
        "id": "bread",
        "display_name": "Bread & Bakery",
        "icon": "🍞",
        "default_shelf_life_days": 5,
        "meal_contexts": ["breakfast", "sandwich"],
        "sort_order": 70,
    },
    {
        "id": "frozen",
        "display_name": "Frozen Foods",
        "icon": "🧊",
        "default_shelf_life_days": 90,
        "meal_contexts": ["cooking"],
        "sort_order": 80,
    },
    {
        "id": "pantry",
        "display_name": "Pantry Staples",
        "icon": "🥫",
        "default_shelf_life_days": 365,
        "meal_contexts": ["cooking", "baking"],
        "sort_order": 90,
    },
    {
        "id": "beverages",
        "display_name": "Beverages",
        "icon": "🥤",
        "default_shelf_life_days": 30,
        "meal_contexts": ["breakfast", "snack"],
        "sort_order": 100,
    },
    {
        "id": "condiments",
        "display_name": "Condiments & Sauces",
        "icon": "🍯",
        "default_shelf_life_days": 180,
        "meal_contexts": ["cooking"],
        "sort_order": 110,
    },
    {
        "id": "snacks",
        "display_name": "Snacks",
        "icon": "🍿",
        "default_shelf_life_days": 60,
        "meal_contexts": ["snack"],
        "sort_order": 120,
    },
]


async def seed_categories(session: AsyncSession) -> None:
    """Seed the database with default categories.

    Uses PostgreSQL's INSERT ... ON CONFLICT DO NOTHING to make this operation
    idempotent. If a category already exists, it will not be updated.

    Args:
        session: Async database session.
    """
    # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING for idempotency
    # This ensures we don't overwrite any manual updates to existing categories
    stmt = insert(Category).values(SEED_CATEGORIES).on_conflict_do_nothing(index_elements=["id"])

    await session.execute(stmt)
