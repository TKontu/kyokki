"""Stock routes for agents (AG2): per-product totals, add, and consume by name.

Names in, decisions out. Every failure is an `AgentError` with a stable ``detail.code``;
the mutations take an optional ``Idempotency-Key`` and replay their first response to it.
"""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AgentError
from app.api.exceptions import handle_integrity_errors
from app.db.session import get_db
from app.schemas.inventory_item import QuickAddRequest, StorageLocation
from app.schemas.stock import (
    StockAddResponse,
    StockConsumeRequest,
    StockConsumeResponse,
    StockRow,
)
from app.services import idempotency
from app.services import stock as stock_service
from app.services.broadcast_helpers import broadcast_inventory_update
from app.services.generic_products import InvalidProductRequest
from app.services.idempotency import IdempotencyClaim, IdempotencyConflict
from app.services.product_lookup import AmbiguousProduct, ProductNotFound
from app.services.shelf_life_on_create import schedule_estimates

router = APIRouter()

ADD_ROUTE = "POST /api/stock/add"
CONSUME_ROUTE = "POST /api/stock/consume"
ADD_HINT = (
    "Add it with POST /api/stock/add (name, category, quantity, unit), or teach an "
    "existing product this name with POST /api/products/{id}/names"
)

IdempotencyKeyHeader = Header(
    None,
    alias="Idempotency-Key",
    max_length=255,
    description="Retry safely: the same key and body within 24 h replays the first answer",
)


def claim_request(
    body: BaseModel, key: str | None, route: str, **path: Any
) -> IdempotencyClaim | None:
    """The idempotency claim of this request: its key over its route, path and body.

    The body is hashed as validated, every field included, so a retry that spells the
    same request differently (``2.0`` for ``2``, a default sent explicitly) replays.
    """
    if not key:
        return None
    payload = {
        "path": {k: str(v) for k, v in path.items()},
        "body": body.model_dump(mode="json", exclude_unset=False),
    }
    return idempotency.claim_for(key, route, payload)


async def replayed(
    db: AsyncSession, claim: IdempotencyClaim | None
) -> JSONResponse | None:
    """The stored answer to this claim, or None to go ahead. A reused key is `conflict`."""
    if claim is None:
        return None
    try:
        stored = await idempotency.replay(db, claim)
    except IdempotencyConflict as exc:
        raise AgentError("conflict", str(exc)) from exc
    if stored is None:
        return None
    return JSONResponse(
        content=stored.body,
        status_code=stored.status_code,
        headers={"Idempotent-Replayed": "true"},
    )


def lookup_error(exc: ProductNotFound | AmbiguousProduct) -> AgentError:
    if isinstance(exc, AmbiguousProduct):
        return AgentError(
            "ambiguous",
            str(exc),
            candidates=[c.model_dump(mode="json") for c in exc.candidates],
        )
    return AgentError("not_found", str(exc), hint=ADD_HINT if exc.by_name else None)


@router.get("", response_model=list[StockRow])
async def list_stock(
    q: str | None = Query(
        None, description="Substring of a canonical, learned or printed name, any case"
    ),
    location: StorageLocation | None = Query(None, description="Only this location"),
    expiring_days: int | None = Query(
        None, description="Only products whose earliest expiry is within N days"
    ),
    category: str | None = Query(None, description="Category id, e.g. dairy"),
    db: AsyncSession = Depends(get_db),
) -> list[StockRow]:
    """What is in the kitchen, one row per product (and unit), soonest to expire first."""
    return await stock_service.stock_summary(
        db, q=q, location=location, expiring_days=expiring_days, category=category
    )


@router.post(
    "/add", response_model=StockAddResponse, status_code=status.HTTP_201_CREATED
)
async def add_stock(
    body: QuickAddRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Quick add for agents: the created item and whether its product was new.

    With an Idempotency-Key, a retry that arrives while the first request still runs
    waits for it and replays its answer: the key is held until that answer is stored.
    A new product is estimated in the background once this has answered (Q19); a replay
    schedules nothing, because the first request already did.

    Errors: 400 `invalid` (unknown product id, a new product without a valid category),
    409 `conflict` (Idempotency-Key reused with another body).
    """
    claim = claim_request(body, idempotency_key, ADD_ROUTE)
    async with idempotency.held(db, claim):
        if (stored := await replayed(db, claim)) is not None:
            return stored
        try:
            async with handle_integrity_errors():
                result = await stock_service.add_stock(db, body, claim=claim)
        except InvalidProductRequest as exc:
            raise AgentError("invalid", str(exc)) from exc

    item = result.item
    await broadcast_inventory_update(
        inventory_item_id=item.id,
        action="created",
        current_quantity=item.current_quantity,
        status=str(item.status),
        product_name=item.product_name,
    )
    if result.product_created:
        schedule_estimates(background_tasks, [item.product_master_id])
    return result


@router.post("/consume", response_model=StockConsumeResponse)
async def consume_stock(
    body: StockConsumeRequest,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Consume an amount of a product by name, first to expire first, across its items.

    Errors: 404 `not_found` (unknown id, or nothing like the name), 409 `ambiguous` (no
    exact name; `candidates` to choose from), 400 `invalid` (the unit fits none of the
    items, or the amount rounds to nothing), 409 `insufficient_stock` (`available` and
    `unit` say how much there is), 409 `conflict` (Idempotency-Key reused with another body).
    A dry run is never remembered against a key.
    """
    claim = (
        None if body.dry_run else claim_request(body, idempotency_key, CONSUME_ROUTE)
    )
    if (stored := await replayed(db, claim)) is not None:
        return stored
    try:
        async with handle_integrity_errors():
            result = await stock_service.consume(db, body, claim=claim)
    except (ProductNotFound, AmbiguousProduct) as exc:
        raise lookup_error(exc) from exc
    except stock_service.InsufficientStock as exc:
        raise AgentError(
            "insufficient_stock", str(exc), available=exc.available, unit=exc.unit
        ) from exc
    except stock_service.InvalidConsume as exc:
        raise AgentError("invalid", str(exc)) from exc

    if not result.dry_run:
        for used in result.consumed:
            await broadcast_inventory_update(
                inventory_item_id=used.item_id,
                action="consumed",
                current_quantity=Decimal(used.remaining),
                status=used.status,
                product_name=result.product_name,
            )
    return result
