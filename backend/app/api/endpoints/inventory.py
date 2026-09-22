"""API endpoints for Inventory CRUD operations."""

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import handle_integrity_errors
from app.crud import inventory_item as crud_inventory
from app.db.session import get_db
from app.schemas.consume import ConsumeRequest
from app.schemas.inventory_item import (
    BulkItemsRequest,
    BulkItemsResponse,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
    InventoryStatus,
    QuickAddRequest,
    StorageLocation,
    UndoPreviewResponse,
    UndoRequest,
    UndoResponse,
    UndoStepResponse,
)
from app.services import undo as undo_service
from app.services.broadcast_helpers import broadcast_inventory_update
from app.services.generic_products import InvalidProductRequest
from app.services.item_status import ItemEvent, ItemFrozen
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


# Declared before `/{item_id}`, which would otherwise take "undo" for an id and answer 422
@router.get("/undo", response_model=UndoPreviewResponse | None)
async def preview_undo(
    db: AsyncSession = Depends(get_db),
) -> UndoPreviewResponse | None:
    """What the header's Undo would reverse next, or null when there is nothing to undo.

    The most recent change to stock - whichever item, whoever made it: a consume, a finish, a
    mark as gone, a cleared shelf (all its items, as one step), a restore or a quantity
    correction. Send its `batch_id` back to undo exactly that.
    """
    found = await undo_service.preview(db)
    if found is None:
        return None
    batch_id, logged_at, steps = found
    return UndoPreviewResponse(
        batch_id=batch_id,
        logged_at=logged_at,
        steps=[
            UndoStepResponse(
                inventory_item_id=step.inventory_item_id,
                product_name=step.product_name,
                unit=step.unit,
                action=step.action,
                quantity_consumed=step.quantity_consumed,
            )
            for step in steps
        ],
    )


@router.post("/undo", response_model=UndoResponse)
async def undo_last_change(
    request: UndoRequest, db: AsyncSession = Depends(get_db)
) -> UndoResponse:
    """Undo the most recent change to stock; press again to step further back.

    Returns:
        - 200: How many items were put back.
        - 409: Nothing to undo, or something newer happened after the preview was shown -
          the caller should fetch the preview again rather than guess.
    """
    try:
        async with handle_integrity_errors():
            items = await undo_service.undo(db, request.batch_id)
    except undo_service.UndoConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    for item in items:
        row: Any = item
        await broadcast_inventory_update(
            inventory_item_id=row.id,
            action="updated",
            current_quantity=row.current_quantity,
            status=row.status,
            product_name=row.product_name,
        )
    return UndoResponse(undone=len(items))


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


async def _move_many(
    db: AsyncSession, ids: list[UUID], event: ItemEvent
) -> BulkItemsResponse:
    """Run a bulk move and tell every open iPad about each row that changed."""
    result = await crud_inventory.move_many(db, ids, event)

    # One message per item, as every other multi-item operation here does. `DELETE
    # /shopping/purchased/all` is the one bulk route that broadcasts nothing, and the other
    # screens never learn of it; that is a bug, not a convention.
    for item in result.changed:
        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="updated",
            current_quantity=item.current_quantity,
            status=item.status,
        )

    return BulkItemsResponse(
        changed=len(result.changed), refused=result.refused, missing=result.missing
    )


@router.post("/discard", response_model=BulkItemsResponse)
async def discard_inventory_items(
    request: BulkItemsRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkItemsResponse:
    """Throw several items away at once - the shelf of expired food, in one tap.

    One transaction, so the shelf is cleared or it is not; a `PATCH` each would be one
    transaction per item and a failure half way would leave no way to tell what happened.

    Each item goes through the same transition a single discard does, so the waste log gets
    exactly one row per item at its remaining quantity. An item already in the bin is counted
    as `refused` rather than failing the request.

    Returns:
        - 200: Counters. `changed + refused + missing` is the number of ids sent.
    """
    async with handle_integrity_errors():
        return await _move_many(db, request.ids, ItemEvent.DISCARD)


@router.post("/restore", response_model=BulkItemsResponse)
async def restore_inventory_items(
    request: BulkItemsRequest,
    db: AsyncSession = Depends(get_db),
) -> BulkItemsResponse:
    """Take several items back out of the bin - the undo for a clear.

    The mirror of discard, and the reason clearing a shelf is safe to offer at all. Items come
    back `opened`, or `empty` when nothing was left: never `sealed`, because they were in the
    bin (H23).

    Returns:
        - 200: Counters, shaped as discard's.
    """
    async with handle_integrity_errors():
        return await _move_many(db, request.ids, ItemEvent.RESTORE)


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
