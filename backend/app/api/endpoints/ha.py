"""Home Assistant REST endpoints (Phase 1, docs/HOME_ASSISTANT_SPEC.md).

Thin: the shapes and the reuse of AG2's stock-by-name and AG6's low-stock logic live in
`services.ha`. Behind AG1's bearer auth like every other `/api` route (`api_router`'s
dependency); the two mutations honour `Idempotency-Key` and broadcast like the rest of the
app's writes.
"""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.stock import (
    IdempotencyKeyHeader,
    claim_request,
    lookup_error,
    replayed,
)
from app.api.errors import AgentError
from app.api.exceptions import handle_integrity_errors
from app.db.session import get_db
from app.schemas.ha import (
    HaConsumeRequest,
    HaConsumeResponse,
    HaExpiringResponse,
    HaLowStockResponse,
    HaShoppingAddRequest,
    HaStatusResponse,
)
from app.schemas.runout import HaRunoutItem, HaRunoutResponse
from app.schemas.shopping_list_item import ShoppingListItemResponse
from app.services import ha as ha_service
from app.services import idempotency, min_stock, shopping_generate
from app.services import runout as runout_service
from app.services import stock as stock_service
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_shopping_list_update,
)
from app.services.product_lookup import AmbiguousProduct, ProductNotFound

router = APIRouter()

CONSUME_ROUTE = "POST /api/ha/consume"
SHOPPING_ADD_ROUTE = "POST /api/ha/shopping/add"


@router.get("/status", response_model=HaStatusResponse)
async def ha_status(db: AsyncSession = Depends(get_db)) -> Any:
    """Inventory counts for HA's REST sensor platform (one call, several sensors)."""
    return await ha_service.status(db)


@router.get("/expiring", response_model=HaExpiringResponse)
async def ha_expiring(
    days: int = Query(3, description="Items expiring within N days"),
    limit: int = Query(10, ge=1, le=100, description="Max items to return"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Items expiring soon, soonest first, for detailed notifications."""
    return await ha_service.expiring(db, days=days, limit=limit)


@router.get("/low-stock", response_model=HaLowStockResponse)
async def ha_low_stock(db: AsyncSession = Depends(get_db)) -> Any:
    """Products below their restock point, for shopping reminders. Writes nothing."""
    return await ha_service.low_stock(db)


@router.get("/runout", response_model=HaRunoutResponse)
async def ha_runout(
    within_days: int | None = Query(
        None, ge=0, description="Only products running out within N days"
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """When each product will run out, for a template sensor. Writes nothing.

    The same forecast `GET /api/stock/runout` returns (`services.runout`), shaped down
    to what a sensor needs - no `active_stock` or `daily_rate`.
    """
    items = await runout_service.forecast(db, within_days=within_days)
    shaped = [
        HaRunoutItem(
            id=item.product_id,
            name=item.name,
            unit=item.unit,
            days_left=item.days_left,
            runs_out_on=item.runs_out_on,
            status=item.status,
        )
        for item in items
    ]
    return HaRunoutResponse(items=shaped, count=len(shaped))


@router.post("/consume", response_model=HaConsumeResponse)
async def ha_consume(
    body: HaConsumeRequest,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Mark stock consumed by product name, amount and unit, for a voice assistant.

    Errors: 404 `not_found` (nothing like the name), 409 `ambiguous` (`candidates` to
    choose from - a voice intent can say so), 400 `invalid` (the unit fits no item, or
    rounds to nothing), 409 `insufficient_stock` (`available` and `unit` say how much
    there is), 409 `conflict` (Idempotency-Key reused with another body).
    """
    claim = claim_request(body, idempotency_key, CONSUME_ROUTE)
    async with idempotency.held(db, claim):
        if (stored := await replayed(db, claim)) is not None:
            return stored
        try:
            async with handle_integrity_errors():
                response, result = await ha_service.consume_by_name(
                    db, body.name, body.amount, body.unit
                )
        except (ProductNotFound, AmbiguousProduct) as exc:
            raise lookup_error(exc) from exc
        except stock_service.InsufficientStock as exc:
            raise AgentError(
                "insufficient_stock", str(exc), available=exc.available, unit=exc.unit
            ) from exc
        except stock_service.InvalidConsume as exc:
            raise AgentError("invalid", str(exc)) from exc

        if claim is not None:
            try:
                await idempotency.remember(
                    db, claim, 200, response.model_dump(mode="json")
                )
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    for used in result.consumed:
        await broadcast_inventory_update(
            inventory_item_id=used.item_id,
            action="consumed",
            current_quantity=Decimal(used.remaining),
            status=used.status,
            product_name=result.product_name,
        )
    await min_stock.after_stock_decrease(db, result.product_id)
    return response


@router.post("/shopping/add", response_model=ShoppingListItemResponse, status_code=201)
async def ha_shopping_add(
    body: HaShoppingAddRequest,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Add an item to the shopping list by name, for a voice assistant.

    `amount`/`unit` default to 1 pcs, `priority` to normal. Errors: 409 `conflict`
    (Idempotency-Key reused with another body).
    """
    item_in = ha_service.shopping_add_item(
        body.name, body.amount, body.unit, body.priority
    )
    claim = claim_request(item_in, idempotency_key, SHOPPING_ADD_ROUTE)
    async with idempotency.held(db, claim):
        if (stored := await replayed(db, claim)) is not None:
            return stored
        async with handle_integrity_errors():
            # Any: the model declares untyped `Column`s, which mypy reads as Column[...].
            item: Any = await shopping_generate.create_item(db, item_in, claim=claim)

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
