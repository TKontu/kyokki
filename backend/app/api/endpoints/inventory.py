"""API endpoints for Inventory CRUD operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import handle_integrity_errors
from app.crud import inventory_item as crud_inventory
from app.db.session import get_db
from app.schemas.consume import ConsumeRequest
from app.schemas.inventory_item import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
)
from app.services.broadcast_helpers import broadcast_inventory_update

router = APIRouter()


@router.get("", response_model=list[InventoryItemResponse])
async def list_inventory(
    location: str | None = Query(None, description="Filter by location"),
    status: str | None = Query(None, description="Filter by status"),
    expiring_days: int | None = Query(
        None, description="Filter items expiring within N days"
    ),
    include_inactive: bool = Query(
        False, description="Include empty and discarded items when no status is given"
    ),
    db: AsyncSession = Depends(get_db),
) -> list[InventoryItemResponse]:
    """Get inventory items with optional filters; empty and discarded are hidden."""
    items = await crud_inventory.get_inventory_items(
        db,
        location=location,
        status=status,
        expiring_days=expiring_days,
        include_inactive=include_inactive,
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
    async with handle_integrity_errors():
        created_item = await crud_inventory.create_inventory_item(db, item)

    await broadcast_inventory_update(
        inventory_item_id=created_item.id,
        action="created",
        current_quantity=created_item.current_quantity,
        status=created_item.status,
        product_name=created_item.product_name,
    )

    return created_item


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

    await broadcast_inventory_update(
        inventory_item_id=item.id,
        action="updated",
        current_quantity=item.current_quantity,
        status=item.status,
        product_name=item.product_name,
    )

    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    item_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Delete an inventory item."""
    # Get item before deletion for broadcast (product relationship is eager-loaded)
    item = await crud_inventory.get_inventory_item(db, item_id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory item with ID '{item_id}' not found",
        )

    product_name = item.product_name
    await crud_inventory.delete_inventory_item(db, item_id)
    await broadcast_inventory_update(
        inventory_item_id=item_id, action="deleted", product_name=product_name
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

        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="consumed",
            current_quantity=item.current_quantity,
            status=item.status,
            product_name=item.product_name,
        )

        return item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
