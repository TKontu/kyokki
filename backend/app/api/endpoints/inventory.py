"""API endpoints for Inventory CRUD operations."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.crud import inventory_item as crud_inventory
from app.schemas.inventory_item import (
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryItemResponse,
)
from app.schemas.consume import ConsumeRequest


router = APIRouter()


@router.get("", response_model=list[InventoryItemResponse])
async def list_inventory(
    location: str | None = Query(None, description="Filter by location"),
    status: str | None = Query(None, description="Filter by status"),
    expiring_days: int | None = Query(
        None, description="Filter items expiring within N days"
    ),
    db: AsyncSession = Depends(get_db),
) -> list[InventoryItemResponse]:
    """Get all inventory items with optional filters."""
    items = await crud_inventory.get_inventory_items(
        db, location=location, status=status, expiring_days=expiring_days
    )
    return items


@router.get("/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    item_id: UUID, db: AsyncSession = Depends(get_db)
) -> InventoryItemResponse:
    """Get a specific inventory item by ID."""
    item = await crud_inventory.get_inventory_item(db, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with ID '{item_id}' not found",
        )
    return item


@router.post(
    "", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED
)
async def create_inventory_item(
    item: InventoryItemCreate, db: AsyncSession = Depends(get_db)
) -> InventoryItemResponse:
    """Create a new inventory item."""
    try:
        return await crud_inventory.create_inventory_item(db, item)
    except IntegrityError as e:
        # Check if it's a foreign key constraint error
        if "product_master" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with ID '{item.product_master_id}' does not exist",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity error",
        )


@router.patch("/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    item_id: UUID,
    item_update: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> InventoryItemResponse:
    """Update an inventory item."""
    item = await crud_inventory.update_inventory_item(db, item_id, item_update)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with ID '{item_id}' not found",
        )
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    item_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete an inventory item."""
    deleted = await crud_inventory.delete_inventory_item(db, item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with ID '{item_id}' not found",
        )


@router.post("/{item_id}/consume", response_model=InventoryItemResponse)
async def consume_inventory_item(
    item_id: UUID,
    consume_request: ConsumeRequest,
    db: AsyncSession = Depends(get_db),
) -> InventoryItemResponse:
    """Consume/reduce quantity from an inventory item."""
    try:
        item = await crud_inventory.consume_inventory_item(
            db, item_id, consume_request.quantity
        )
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Inventory item with ID '{item_id}' not found",
            )
        return item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
