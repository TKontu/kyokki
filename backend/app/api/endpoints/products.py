"""API endpoints for Product CRUD operations."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.crud import product_master as crud_product
from app.schemas.product_master import (
    ProductMasterCreate,
    ProductMasterUpdate,
    ProductMasterResponse,
)


router = APIRouter()


@router.get("", response_model=list[ProductMasterResponse])
async def list_products(
    search: str | None = Query(None, description="Search by product name"),
    db: AsyncSession = Depends(get_db),
) -> list[ProductMasterResponse]:
    """Get all products with optional search filter."""
    products = await crud_product.get_products(db, search=search)
    return products


@router.get("/barcode/{barcode}", response_model=ProductMasterResponse)
async def lookup_by_barcode(
    barcode: str, db: AsyncSession = Depends(get_db)
) -> ProductMasterResponse:
    """Lookup a product by barcode/OFF product ID."""
    product = await crud_product.get_product_by_barcode(db, barcode)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with barcode '{barcode}' not found",
        )
    return product


@router.get("/{product_id}", response_model=ProductMasterResponse)
async def get_product(
    product_id: UUID, db: AsyncSession = Depends(get_db)
) -> ProductMasterResponse:
    """Get a specific product by ID."""
    product = await crud_product.get_product(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )
    return product


@router.post("", response_model=ProductMasterResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product: ProductMasterCreate, db: AsyncSession = Depends(get_db)
) -> ProductMasterResponse:
    """Create a new product."""
    try:
        return await crud_product.create_product(db, product)
    except IntegrityError as e:
        # Check if it's a foreign key constraint error
        if "category" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category '{product.category}' does not exist",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity error",
        )


@router.patch("/{product_id}", response_model=ProductMasterResponse)
async def update_product(
    product_id: UUID,
    product_update: ProductMasterUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProductMasterResponse:
    """Update a product."""
    product = await crud_product.update_product(db, product_id, product_update)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete a product."""
    deleted = await crud_product.delete_product(db, product_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )
