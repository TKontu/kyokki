"""Seed data for product categories.

Run inside the API container to seed a fresh database:

    python -m app.db.seed_categories
"""

import asyncio

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.category import Category

# Seed data based on common food categories and their typical shelf lives.
# `frozen_shelf_life_days` is spelled out for every category, None included: the bulk
# insert needs one shape for all rows, and None is a statement rather than an omission -
# freezing a bottle of squash is not a thing this models (Q12, DEC-10).
#
# `default_shelf_life_days` is a placeholder: a product gets its own number from the cook or
# the catalog estimate (Q11). It errs short for perishables - an early warning wastes less
# than a late one - but not absurdly (H57, Q15: tea and juice used to expire in a month).
# Changing one here reaches new databases only; `e8b4f1c62a90` shows how to move deployed ones.
SEED_CATEGORIES = [
    {
        "id": "meat",
        "display_name": "Meat & Poultry",
        "icon": "🥩",
        "default_shelf_life_days": 5,
        "frozen_shelf_life_days": 180,
        "sort_order": 10,
    },
    {
        "id": "fish",
        "display_name": "Fish & Seafood",
        "icon": "🐟",
        "default_shelf_life_days": 3,
        "frozen_shelf_life_days": 120,
        "sort_order": 20,
    },
    {
        "id": "dairy",
        "display_name": "Dairy & Eggs",
        "icon": "🥛",
        "default_shelf_life_days": 10,
        "frozen_shelf_life_days": 90,
        "sort_order": 30,
    },
    {
        "id": "cheese",
        "display_name": "Cheese",
        "icon": "🧀",
        "default_shelf_life_days": 25,
        "frozen_shelf_life_days": 180,
        "sort_order": 40,
    },
    {
        "id": "produce",
        "display_name": "Fresh Produce",
        "icon": "🥬",
        "default_shelf_life_days": 7,
        "frozen_shelf_life_days": 240,
        "sort_order": 50,
    },
    {
        "id": "fruits",
        "display_name": "Fruits",
        "icon": "🍎",
        "default_shelf_life_days": 7,
        "frozen_shelf_life_days": 240,
        "sort_order": 60,
    },
    {
        "id": "bread",
        "display_name": "Bread & Bakery",
        "icon": "🍞",
        "default_shelf_life_days": 5,
        "frozen_shelf_life_days": 90,
        "sort_order": 70,
    },
    {
        # H55: soups, casseroles, a supermarket lasagne. Filed by what they are rather
        # than what is in them - the fish soup on the homelab had ended up under frozen.
        "id": "ready_meals",
        "display_name": "Ready Meals",
        "icon": "🍲",
        "default_shelf_life_days": 4,
        "frozen_shelf_life_days": 90,
        "sort_order": 75,
    },
    {
        "id": "frozen",
        "display_name": "Frozen Foods",
        "icon": "🧊",
        "default_shelf_life_days": 90,
        "frozen_shelf_life_days": 365,
        "sort_order": 80,
    },
    {
        "id": "pantry",
        "display_name": "Pantry Staples",
        "icon": "🥫",
        "default_shelf_life_days": 365,
        "frozen_shelf_life_days": None,
        "sort_order": 90,
    },
    {
        "id": "beverages",
        "display_name": "Beverages",
        "icon": "🥤",
        "default_shelf_life_days": 180,
        "frozen_shelf_life_days": None,
        "sort_order": 100,
    },
    {
        "id": "condiments",
        "display_name": "Condiments & Sauces",
        "icon": "🍯",
        "default_shelf_life_days": 180,
        "frozen_shelf_life_days": None,
        "sort_order": 110,
    },
    {
        "id": "snacks",
        "display_name": "Snacks",
        "icon": "🍿",
        "default_shelf_life_days": 90,
        "frozen_shelf_life_days": None,
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
    stmt = (
        insert(Category)
        .values(SEED_CATEGORIES)
        .on_conflict_do_nothing(index_elements=["id"])
    )

    await session.execute(stmt)


async def main() -> None:
    """Seed categories using the application's database settings and commit."""
    async with AsyncSessionLocal() as session:
        await seed_categories(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
