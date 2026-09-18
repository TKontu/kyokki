"""API endpoints for Category CRUD operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import handle_integrity_errors, reference_conflict_detail
from app.crud import category as crud_category
from app.db.session import get_db
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter()


@router.get("", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[CategoryResponse]:
    """Get all categories sorted by sort_order."""
    categories = await crud_category.get_categories(db)
    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str, db: AsyncSession = Depends(get_db)
) -> CategoryResponse:
    """Get a specific category by ID."""
    category = await crud_category.get_category(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found",
        )
    return category


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category: CategoryCreate, db: AsyncSession = Depends(get_db)
) -> CategoryResponse:
    """Create a new category."""
    # The hand-rolled handler here called *every* integrity error a duplicate id
    # and answered 400; the shared one classifies by the asyncpg exception type.
    async with handle_integrity_errors():
        return await crud_category.create_category(db, category)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_update: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Update a category."""
    async with handle_integrity_errors():
        category = await crud_category.update_category(db, category_id, category_update)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found",
        )
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a category, unless products still use it."""
    references = await crud_category.references_to_category(db, category_id)
    if references:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=reference_conflict_detail(references),
        )

    async with handle_integrity_errors():
        deleted = await crud_category.delete_category(db, category_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found",
        )
