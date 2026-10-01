"""Server-Sent Events endpoint for real-time updates (A5).

``GET /api/events`` is the browser-reachable twin of ``/api/ws``: the iPad PWA cannot
hold an API token (AG1), so it cannot open a WebSocket straight to the backend (browsers
cannot set WebSocket headers, and the token must not sit in a URL the browser sees). A
plain GET, by contrast, passes through ``frontend/middleware.ts`` like any other request,
which attaches the server-side token before the Next.js rewrite proxies it here.

Fed by the same ``ConnectionManager`` the WebSocket endpoint uses, which in turn is fed by
the single Redis listener in ``app.main`` — this endpoint does not open its own Redis
subscription, so there is nothing per-client to leak there. Each connected stream owns one
bounded queue (``ConnectionManager.subscribe_sse``); cleanup happens in the ``finally``
block below, so a client that disconnects does not leak its queue either.
"""

import asyncio
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.services.websockets import manager

logger = get_logger(__name__)
router = APIRouter()

# How often we check request.is_disconnected() while idle. Starlette's check is a
# near-instant non-blocking poll of the ASGI receive channel, so this is cheap; it
# bounds how long a dead connection's queue lingers before cleanup.
DISCONNECT_POLL_SECONDS = 1.0
# How often an idle stream gets a heartbeat comment, to keep the Next.js rewrite
# proxy (and any other intermediary) from treating the connection as dead.
HEARTBEAT_INTERVAL_SECONDS = 15.0


async def _event_stream(request: Request) -> AsyncGenerator[str, None]:
    queue = manager.subscribe_sse()
    last_heartbeat = time.monotonic()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(
                    queue.get(), timeout=DISCONNECT_POLL_SECONDS
                )
            except TimeoutError:
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    last_heartbeat = now
                    yield ": heartbeat\n\n"
                continue
            last_heartbeat = time.monotonic()
            # Never log the payload itself (product names, quantities) at INFO.
            yield f"data: {message}\n\n"
    finally:
        manager.unsubscribe_sse(queue)
        logger.info("sse_client_disconnected")


@router.get("/events")
async def events_stream(request: Request) -> StreamingResponse:
    """Stream the same broadcast messages as ``/api/ws``, as Server-Sent Events.

    One ``data:`` line per broadcast message (the existing
    ``{"type", "timestamp", "entity_id", "data"}`` shape, JSON-encoded), plus a
    ``resync`` message in place of one that was dropped because this client fell
    behind. Read scope under AG1, like any GET.
    """
    logger.info("sse_client_connected")
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
