"""API endpoints for Inventory CRUD operations."""

from decimal import Decimal
from typing import cast
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
    InventoryStatus,
    QuickAddRequest,
    StorageLocation,
)
from app.services.broadcast_helpers import broadcast_inventory_update
from app.services.generic_products import InvalidProductRequest
from app.services.item_status import ItemFrozen
from app.services.quick_add import quick_add

router = APIRouter()


@router.get("", response_model=list[InventoryItemResponse])
async def list_inventory(
    # H24 closed the request bodies and left the query string open: `?status=banana` used to
    # answer an empty list rather than a 422, which reads as "no such items" instead of "no
    # such status". The screen that lists thrown-away items filters on this.
    location: StorageLocation | None = Query(None, description="Filter by location"),
    status: InventoryStatus | None = Query(None, description="Filter by status"),
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
        inventory_item_id=cast(UUID, created_item.id),
        action="created",
        current_quantity=cast(Decimal, created_item.current_quantity),
        status=str(created_item.status),
        product_name=created_item.product_name,
    )

    return created_item


@router.post(
    "/quick-add",
    response_model=InventoryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def quick_add_inventory_item(
    request: QuickAddRequest, db: AsyncSession = Depends(get_db)
) -> InventoryItemResponse:
    """Add stock by hand for an existing or new generic product in one call.

    Raises:
        HTTPException 400: Unknown product, or a new product without a valid category.
    """
    try:
        async with handle_integrity_errors():
            result = await quick_add(db, request)
    except InvalidProductRequest as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    item = result.item
    await broadcast_inventory_update(
        inventory_item_id=cast(UUID, item.id),
        action="created",
        current_quantity=cast(Decimal, item.current_quantity),
        status=str(item.status),
        product_name=item.product_name,
    )
    return InventoryItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    item_id: UUID,
    item_update: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> InventoryItemResponse:
    """Update an inventory item.

    An item that has been thrown away is frozen: it answers 409 rather than quietly walking
    back into the kitchen (H23). Sending it an active status is how to bring it back.
    """
    try:
        async with handle_integrity_errors():
            item = await crud_inventory.update_inventory_item(db, item_id, item_update)
    except ItemFrozen as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
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
    async with handle_integrity_errors():
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
    """Consume/reduce quantity from an inventory item.

    Returns:
        - 200: Consumed; the body is the item as it now stands.
        - 400: More than is there, an amount that rounds to nothing, or a unit that is not
          the same kind of measure as the item's.
        - 404: No such item.
        - 409: The item has been thrown away (H23).
    """
    try:
        async with handle_integrity_errors():
            item = await crud_inventory.consume_inventory_item(
                db, item_id, consume_request.quantity, consume_request.unit
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
    except ItemFrozen as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
