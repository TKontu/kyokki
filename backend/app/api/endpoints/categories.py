"""API endpoints for Category CRUD operations."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.crud import category as crud_category
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse


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
    try:
        return await crud_category.create_category(db, category)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with ID '{category.id}' already exists",
        )


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_update: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Update a category."""
    category = await crud_category.update_category(db, category_id, category_update)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found",
        )
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: str, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete a category."""
    deleted = await crud_category.delete_category(db, category_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found",
        )
