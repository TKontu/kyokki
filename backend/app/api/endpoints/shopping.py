"""Shopping list API endpoints."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.stock import IdempotencyKeyHeader, claim_request, replayed
from app.api.errors import AgentError
from app.api.exceptions import handle_integrity_errors
from app.core.logging import get_logger
from app.crud.shopping_list_item import shopping_list_item
from app.db.session import get_db
from app.schemas.shopping_list_item import (
    ShoppingGenerateLine,
    ShoppingGenerateRequest,
    ShoppingGenerateResponse,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingListItemUpdate,
)
from app.services import shopping_generate
from app.services.broadcast_helpers import broadcast_shopping_list_update

router = APIRouter()
logger = get_logger(__name__)

GENERATE_ROUTE = "POST /api/shopping/generate"
GeneratedAction = Literal["created", "updated"]
EXPORT_MEDIA_TYPES = {"text": "text/plain", "markdown": "text/markdown"}


@router.get("/", response_model=list[ShoppingListItemResponse])
async def get_shopping_list(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum items to return"),
    priority: str | None = Query(
        None, description="Filter by priority: urgent, normal, low"
    ),
    include_purchased: bool = Query(False, description="Include purchased items"),
    db: AsyncSession = Depends(get_db),
):
    """Get shopping list items with optional filtering.

    By default, only returns unpurchased items ordered by priority (urgent first).
    """
    logger.info(
        "get_shopping_list",
        extra={
            "skip": skip,
            "limit": limit,
            "priority": priority,
            "include_purchased": include_purchased,
        },
    )

    items = await shopping_list_item.get_all(
        db,
        skip=skip,
        limit=limit,
        priority=priority,
        include_purchased=include_purchased,
    )

    return items


@router.get("/urgent", response_model=list[ShoppingListItemResponse])
async def get_urgent_items(
    db: AsyncSession = Depends(get_db),
):
    """Get all urgent unpurchased items.

    Useful for quick access to critical shopping items.
    """
    logger.info("get_urgent_items")

    items = await shopping_list_item.get_urgent_items(db)
    return items


# Static paths before /{item_id}, which would otherwise take "export" for an id and 422.
@router.get(
    "/export",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {"text/plain": {}, "text/markdown": {}}},
        400: {"description": "`invalid`: an unknown format"},
    },
)
async def export_shopping_list(
    format: str = Query(
        "text", description="text (`- name quantity unit`) or markdown (a checklist)"
    ),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """The open list, urgent first and then by name, as plain text or Markdown (UTF-8).

    Errors: 400 `invalid` (an unknown format).
    """
    try:
        text = await shopping_generate.export(db, format)
    except ValueError as exc:
        raise AgentError("invalid", str(exc)) from exc
    return PlainTextResponse(text, media_type=EXPORT_MEDIA_TYPES[format])


@router.post("/generate", response_model=ShoppingGenerateResponse)
async def generate_shopping_list(
    body: ShoppingGenerateRequest,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Put what the kitchen is short of on the list, merged into the open items.

    `low_stock`: every product with a `min_stock_quantity` whose stock is below it needs
    its `reorder_quantity`, or the shortfall when that is not set. An open item for the
    product is raised to the need instead of being joined by a second one.

    Errors: 400 `invalid` (no source, or an unknown one), 409 `conflict`
    (Idempotency-Key reused with another body). A dry run is never remembered.
    """
    claim = (
        None if body.dry_run else claim_request(body, idempotency_key, GENERATE_ROUTE)
    )
    if (stored := await replayed(db, claim)) is not None:
        return stored
    try:
        async with handle_integrity_errors():
            result = await shopping_generate.generate(
                db, body.sources, dry_run=body.dry_run, claim=claim
            )
    except shopping_generate.InvalidGenerate as exc:
        raise AgentError("invalid", str(exc)) from exc

    if not result.dry_run:
        touched: list[tuple[GeneratedAction, ShoppingGenerateLine]] = [
            ("created", line) for line in result.added
        ] + [("updated", line) for line in result.updated]
        for action, line in touched:
            item: Any = await shopping_list_item.get(db, id=line.item_id)
            if item is None:
                continue
            await broadcast_shopping_list_update(
                shopping_list_item_id=item.id,
                action=action,
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                priority=item.priority,
                is_purchased=item.is_purchased,
            )
    return result


@router.get("/{item_id}", response_model=ShoppingListItemResponse)
async def get_shopping_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific shopping list item by ID."""
    logger.info("get_shopping_item", extra={"item_id": str(item_id)})

    item = await shopping_list_item.get(db, id=item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item {item_id} not found",
        )

    return item


@router.post(
    "/", response_model=ShoppingListItemResponse, status_code=status.HTTP_201_CREATED
)
async def create_shopping_item(
    item_in: ShoppingListItemCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new shopping list item.

    Can be either:
    - Linked to a product_master (product_master_id provided)
    - Free-text item (product_master_id is null)
    """
    logger.info(
        "create_shopping_item",
        extra={
            # "name" is reserved on logging.LogRecord; using it raises KeyError.
            "item_name": item_in.name,
            "priority": item_in.priority,
            "source": item_in.source,
        },
    )

    # Validate priority
    if item_in.priority not in ["urgent", "normal", "low"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid priority: {item_in.priority}. Must be urgent, normal, or low.",
        )

    # `source` and `priority` used to be checked here by hand, which was a third way of
    # spelling a vocabulary alongside Literal and StrEnum. `ShoppingSource` does it at the
    # schema now, so an unknown value never reaches this function (H24).

    async with handle_integrity_errors():
        item = await shopping_list_item.create(db, obj_in=item_in)

    # Broadcast creation
    await broadcast_shopping_list_update(
        shopping_list_item_id=item.id,
        action="created",
        name=item.name,
        quantity=item.quantity,
        unit=item.unit,
        priority=item.priority,
        is_purchased=False,
    )

    return item


@router.patch("/{item_id}", response_model=ShoppingListItemResponse)
async def update_shopping_item(
    item_id: UUID,
    item_in: ShoppingListItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a shopping list item.

    Can update name, quantity, unit, priority, or purchase status.
    """
    logger.info("update_shopping_item", extra={"item_id": str(item_id)})

    item = await shopping_list_item.get(db, id=item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item {item_id} not found",
        )

    async with handle_integrity_errors():
        updated_item = await shopping_list_item.update(db, db_obj=item, obj_in=item_in)

    # Broadcast update
    await broadcast_shopping_list_update(
        shopping_list_item_id=updated_item.id,
        action="updated",
        name=updated_item.name,
        quantity=updated_item.quantity,
        unit=updated_item.unit,
        priority=updated_item.priority,
        is_purchased=updated_item.is_purchased,
    )

    return updated_item


@router.post("/{item_id}/purchase", response_model=ShoppingListItemResponse)
async def mark_item_purchased(
    item_id: UUID,
    purchased: bool = Query(
        True, description="Mark as purchased (true) or unpurchased (false)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Mark a shopping list item as purchased or unpurchased.

    When marked as purchased, sets is_purchased=true and records purchased_at timestamp.
    When marked as unpurchased, sets is_purchased=false and clears purchased_at.
    """
    logger.info(
        "mark_item_purchased",
        extra={"item_id": str(item_id), "purchased": purchased},
    )

    async with handle_integrity_errors():
        item = await shopping_list_item.mark_purchased(
            db, item_id=item_id, purchased=purchased
        )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item {item_id} not found",
        )

    # Broadcast purchase status change
    await broadcast_shopping_list_update(
        shopping_list_item_id=item.id,
        action="purchased",
        name=item.name,
        quantity=item.quantity,
        unit=item.unit,
        priority=item.priority,
        is_purchased=item.is_purchased,
    )

    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a shopping list item."""
    logger.info("delete_shopping_item", extra={"item_id": str(item_id)})

    item = await shopping_list_item.get(db, id=item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item {item_id} not found",
        )

    # Store item data before deletion for broadcast
    item_name = item.name
    item_quantity = item.quantity
    item_unit = item.unit
    item_priority = item.priority

    async with handle_integrity_errors():
        await shopping_list_item.remove(db, id=item_id)

    # Broadcast deletion
    await broadcast_shopping_list_update(
        shopping_list_item_id=item_id,
        action="deleted",
        name=item_name,
        quantity=item_quantity,
        unit=item_unit,
        priority=item_priority,
        is_purchased=None,
    )

    return None


@router.delete("/purchased/all", status_code=status.HTTP_200_OK)
async def delete_all_purchased(
    db: AsyncSession = Depends(get_db),
):
    """Delete all purchased items from the shopping list.

    Useful for clearing completed purchases in bulk.
    """
    logger.info("delete_all_purchased")

    async with handle_integrity_errors():
        deleted_count = await shopping_list_item.delete_purchased(db)

    logger.info("deleted_purchased_items", extra={"count": deleted_count})

    return {"deleted_count": deleted_count}
