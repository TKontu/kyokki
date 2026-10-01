"""WebSocket connection manager for real-time updates."""

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger(__name__)

# Per-SSE-client bounded queue (A5). A slow client that falls this far behind
# gets the oldest message dropped and a ``resync`` event in its place, rather
# than growing without bound or blocking the broadcast for everyone else.
SSE_QUEUE_MAXSIZE = 32


def _resync_message() -> str:
    """The event an overflowed SSE client gets instead of the message it missed."""
    return json.dumps(
        {
            "type": "resync",
            "timestamp": datetime.now(UTC).isoformat(),
            "entity_id": None,
            "data": {},
        }
    )


class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # SSE (A5) is fed from the same broadcast() calls as the WebSocket
        # clients, one bounded asyncio.Queue per connected stream.
        self._sse_subscribers: list[asyncio.Queue[str]] = []

    def subscribe_sse(self) -> "asyncio.Queue[str]":
        """Register a new SSE client and return its message queue.

        The caller must call ``unsubscribe_sse`` with the same queue when the
        client disconnects (normally from a ``finally`` block), or the queue
        leaks for the life of the process.
        """
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=SSE_QUEUE_MAXSIZE)
        self._sse_subscribers.append(queue)
        logger.info(
            "sse_client_connected",
            extra={"total_sse_clients": len(self._sse_subscribers)},
        )
        return queue

    def unsubscribe_sse(self, queue: "asyncio.Queue[str]") -> None:
        """Remove an SSE client's queue. Safe to call more than once."""
        if queue in self._sse_subscribers:
            self._sse_subscribers.remove(queue)
            logger.info(
                "sse_client_disconnected",
                extra={"total_sse_clients": len(self._sse_subscribers)},
            )

    def _publish_sse(self, message: str) -> None:
        """Fan a raw JSON message out to every subscribed SSE queue.

        Never logs the payload (it may carry product names) at INFO.
        """
        for queue in self._sse_subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(_resync_message())
                logger.warning(
                    "sse_client_overflow",
                    extra={"total_sse_clients": len(self._sse_subscribers)},
                )

    async def connect(self, websocket: WebSocket):
        """Accept WebSocket connection and add to active connections.

        Args:
            websocket: WebSocket connection to add.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "websocket_connected",
            extra={"total_connections": len(self.active_connections)},
        )

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket from active connections.

        Args:
            websocket: WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                "websocket_disconnected",
                extra={"total_connections": len(self.active_connections)},
            )

    async def broadcast(self, message: str):
        """Broadcast message to all connected clients with error handling.

        Automatically removes disconnected clients.

        Args:
            message: Text message to broadcast.
        """
        disconnected_clients = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    extra={"error": str(e), "operation": "broadcast"},
                )
                disconnected_clients.append(connection)

        # Clean up disconnected clients
        for client in disconnected_clients:
            self.disconnect(client)

        # SSE clients (A5) share this same broadcast, never the raw WebSocket.
        self._publish_sse(message)

        logger.debug(
            "broadcast_complete",
            extra={
                "message_length": len(message),
                "recipients": len(self.active_connections),
                "sse_recipients": len(self._sse_subscribers),
            },
        )

    async def send_json(self, websocket: WebSocket, data: dict[str, Any]):
        """Send JSON message to a specific client.

        Args:
            websocket: Target WebSocket connection.
            data: Dictionary to send as JSON.
        """
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(
                "websocket_send_json_failed", extra={"error": str(e)}, exc_info=True
            )
            self.disconnect(websocket)

    async def broadcast_json(self, data: dict[str, Any]):
        """Broadcast JSON data to all connected clients.

        Args:
            data: Dictionary to broadcast as JSON.
        """
        message = json.dumps(data)
        await self.broadcast(message)


manager = ConnectionManager()
