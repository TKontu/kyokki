"""CRUD operations for Category model."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


async def get_categories(db: AsyncSession) -> list[Category]:
    """Get all categories sorted by sort_order.

    Args:
        db: Database session.

    Returns:
        List of all categories.
    """
    result = await db.execute(
        select(Category).order_by(Category.sort_order)
    )
    return list(result.scalars().all())


async def get_category(db: AsyncSession, category_id: str) -> Category | None:
    """Get a category by ID.

    Args:
        db: Database session.
        category_id: Category ID.

    Returns:
        Category if found, None otherwise.
    """
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    return result.scalar_one_or_none()


async def create_category(db: AsyncSession, category: CategoryCreate) -> Category:
    """Create a new category.

    Args:
        db: Database session.
        category: Category data.

    Returns:
        Created category.

    Raises:
        IntegrityError: If category with same ID already exists.
    """
    db_category = Category(**category.model_dump())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    return db_category


async def update_category(
    db: AsyncSession, category_id: str, category_update: CategoryUpdate
) -> Category | None:
    """Update a category.

    Args:
        db: Database session.
        category_id: Category ID.
        category_update: Fields to update.

    Returns:
        Updated category if found, None otherwise.
    """
    db_category = await get_category(db, category_id)
    if not db_category:
        return None

    # Update only provided fields
    update_data = category_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_category, field, value)

    await db.commit()
    await db.refresh(db_category)
    return db_category


async def delete_category(db: AsyncSession, category_id: str) -> bool:
    """Delete a category.

    Args:
        db: Database session.
        category_id: Category ID.

    Returns:
        True if deleted, False if not found.
    """
    db_category = await get_category(db, category_id)
    if not db_category:
        return False

    await db.delete(db_category)
    await db.commit()
    return True
