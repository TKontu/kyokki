"""Stock routes for agents (AG2): per-product totals, add, consume and discard-expired.

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
    DiscardExpiredRequest,
    DiscardExpiredResponse,
    StockAddResponse,
    StockConsumeRequest,
    StockConsumeResponse,
    StockRow,
)
from app.services import idempotency
from app.services import stock as stock_service
from app.services.broadcast_helpers import broadcast_inventory_update
from app.services.generic_products import InvalidProductRequest, UnknownProduct
from app.services.idempotency import IdempotencyClaim, IdempotencyConflict
from app.services.product_lookup import AmbiguousProduct, ProductNotFound
from app.services.shelf_life_on_create import schedule_estimates

router = APIRouter()

ADD_ROUTE = "POST /api/stock/add"
CONSUME_ROUTE = "POST /api/stock/consume"
DISCARD_EXPIRED_ROUTE = "POST /api/stock/discard-expired"
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

    With an Idempotency-Key, the item and the stored answer commit together (Q24): a
    crash during the broadcast that follows - even a Redis hang - cannot duplicate the
    item, because a retry finds the key already there and replays. A new product is
    estimated in the background once this has answered (Q19); a replay schedules
    nothing, because the first request already did.

    Errors: 404 `not_found` (unknown product id, as stock/consume answers it), 400
    `invalid` (a new product without a valid category), 409 `conflict` (Idempotency-Key
    reused with another body).
    """
    claim = claim_request(body, idempotency_key, ADD_ROUTE)
    if (stored := await replayed(db, claim)) is not None:
        return stored
    try:
        async with handle_integrity_errors():
            result = await stock_service.add_stock(db, body, claim=claim)
    except UnknownProduct as exc:
        raise AgentError("not_found", str(exc)) from exc
    except InvalidProductRequest as exc:
        raise AgentError("invalid", str(exc)) from exc

    item = result.response.item
    await broadcast_inventory_update(
        inventory_item_id=item.id,
        action="created",
        current_quantity=item.current_quantity,
        status=str(item.status),
        product_name=item.product_name,
    )
    for sibling in result.moved:
        await broadcast_inventory_update(
            inventory_item_id=sibling.id,
            action="updated",
            current_quantity=sibling.current_quantity,
            status=str(sibling.status),
            product_name=item.product_name,
        )
    if result.product_created:
        schedule_estimates(background_tasks, [item.product_master_id])
    return result.response


@router.post("/discard-expired", response_model=DiscardExpiredResponse)
async def discard_expired_stock(
    body: DiscardExpiredRequest,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Throw away everything past its expiry date (AG7 task 6), by name, not by id.

    "Expired" is the iPad's expired shelf rule, reused rather than restated: an active
    item whose expiry date is before today. A dry run answers with what would be
    discarded and changes nothing; a real run moves each item through the same
    status-machine transition `/inventory/discard` applies, so it is logged as `discard`
    in `consumption_log`, can be undone by the general undo, and shows up on the Gone
    screen. With an Idempotency-Key, the discards and the stored answer commit together
    (Q24), exactly as `stock add`'s do; a dry run is never remembered against a key, as
    `stock/consume`'s isn't.

    Errors: 409 `conflict` (Idempotency-Key reused with another body).
    """
    claim = (
        None
        if body.dry_run
        else claim_request(body, idempotency_key, DISCARD_EXPIRED_ROUTE)
    )
    if (stored := await replayed(db, claim)) is not None:
        return stored
    async with handle_integrity_errors():
        result = await stock_service.discard_expired(
            db, location=body.location, dry_run=body.dry_run, claim=claim
        )

    for item in result.changed:
        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="updated",
            current_quantity=item.current_quantity,
            status=item.status,
        )
    return result.response


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
