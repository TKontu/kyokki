"""API endpoints for Inventory CRUD operations."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud import inventory_item as crud_inventory
from app.db.session import get_db
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.consume import ConsumeRequest
from app.schemas.inventory_item import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
)
from app.services.broadcast_helpers import broadcast_inventory_update


router = APIRouter()


async def _get_product_name(db: AsyncSession, item) -> str | None:
    """Get product name for broadcast display.

    Args:
        db: Database session.
        item: Inventory item.

    Returns:
        Product canonical name or None if not found.
    """
    try:
        if hasattr(item, 'product_master') and item.product_master:
            return item.product_master.canonical_name
        # Query if relationship not loaded
        result = await db.execute(
            select(ProductMaster).where(ProductMaster.id == item.product_master_id)
        )
        product = result.scalar_one_or_none()
        return product.canonical_name if product else None
    except Exception:
        return None


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
        created_item = await crud_inventory.create_inventory_item(db, item)

        # Broadcast inventory creation
        product_name = await _get_product_name(db, created_item)
        await broadcast_inventory_update(
            inventory_item_id=created_item.id,
            action="created",
            current_quantity=created_item.current_quantity,
            status=created_item.status,
            product_name=product_name
        )

        return created_item
    except IntegrityError as e:
        # Check if it's a foreign key constraint error
        if "product_master" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with ID '{item.product_master_id}' does not exist",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity error",
        ) from e


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

    # Broadcast inventory update
    product_name = await _get_product_name(db, item)
    await broadcast_inventory_update(
        inventory_item_id=item.id,
        action="updated",
        current_quantity=item.current_quantity,
        status=item.status,
        product_name=product_name
    )

    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    item_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete an inventory item."""
    # Get item before deletion for broadcast (with product relationship loaded)
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.id == item_id)
        .options(selectinload(InventoryItem.product_master))
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with ID '{item_id}' not found",
        )

    product_name = await _get_product_name(db, item)

    # Delete the item
    deleted = await crud_inventory.delete_inventory_item(db, item_id)

    # Broadcast deletion
    await broadcast_inventory_update(
        inventory_item_id=item_id,
        action="deleted",
        product_name=product_name
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

        # Broadcast consumption update
        product_name = await _get_product_name(db, item)
        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="consumed",
            current_quantity=item.current_quantity,
            status=item.status,
            product_name=product_name
        )

        return item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
