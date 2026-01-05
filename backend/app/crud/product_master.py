"""CRUD operations for ProductMaster model."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.product_master import ProductMaster
from app.schemas.product_master import ProductMasterCreate, ProductMasterUpdate


async def get_products(
    db: AsyncSession, search: str | None = None
) -> list[ProductMaster]:
    """Get all products with optional search filter.

    Args:
        db: Database session.
        search: Optional search string to filter by canonical_name.

    Returns:
        List of products matching the filter.
    """
    query = select(ProductMaster)

    if search:
        query = query.where(ProductMaster.canonical_name.ilike(f"%{search}%"))

    query = query.order_by(ProductMaster.canonical_name)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Get a product by ID.

    Args:
        db: Database session.
        product_id: Product UUID.

    Returns:
        Product if found, None otherwise.
    """
    result = await db.execute(
        select(ProductMaster).where(ProductMaster.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_barcode(
    db: AsyncSession, barcode: str
) -> ProductMaster | None:
    """Get a product by barcode (off_product_id).

    Args:
        db: Database session.
        barcode: Barcode/OFF product ID.

    Returns:
        Product if found, None otherwise.
    """
    result = await db.execute(
        select(ProductMaster).where(ProductMaster.off_product_id == barcode)
    )
    return result.scalar_one_or_none()


async def create_product(
    db: AsyncSession, product: ProductMasterCreate
) -> ProductMaster:
    """Create a new product.

    Args:
        db: Database session.
        product: Product data.

    Returns:
        Created product.

    Raises:
        IntegrityError: If foreign key constraint fails (invalid category).
    """
    db_product = ProductMaster(**product.model_dump())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product


async def update_product(
    db: AsyncSession, product_id: UUID, product_update: ProductMasterUpdate
) -> ProductMaster | None:
    """Update a product.

    Args:
        db: Database session.
        product_id: Product UUID.
        product_update: Fields to update.

    Returns:
        Updated product if found, None otherwise.
    """
    db_product = await get_product(db, product_id)
    if not db_product:
        return None

    # Update only provided fields
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)

    await db.commit()
    await db.refresh(db_product)
    return db_product


async def delete_product(db: AsyncSession, product_id: UUID) -> bool:
    """Delete a product.

    Args:
        db: Database session.
        product_id: Product UUID.

    Returns:
        True if deleted, False if not found.
    """
    db_product = await get_product(db, product_id)
    if not db_product:
        return False

    await db.delete(db_product)
    await db.commit()
    return True
