"""WebSocket connection manager for real-time updates."""
import json
from typing import List, Dict, Any
from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept WebSocket connection and add to active connections.

        Args:
            websocket: WebSocket connection to add.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", extra={"total_connections": len(self.active_connections)})

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket from active connections.

        Args:
            websocket: WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("websocket_disconnected", extra={"total_connections": len(self.active_connections)})

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
                    extra={
                        "error": str(e),
                        "operation": "broadcast"
                    }
                )
                disconnected_clients.append(connection)

        # Clean up disconnected clients
        for client in disconnected_clients:
            self.disconnect(client)

        logger.debug(
            "broadcast_complete",
            extra={
                "message_length": len(message),
                "recipients": len(self.active_connections)
            }
        )

    async def send_json(self, websocket: WebSocket, data: Dict[str, Any]):
        """Send JSON message to a specific client.

        Args:
            websocket: Target WebSocket connection.
            data: Dictionary to send as JSON.
        """
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.error(
                "websocket_send_json_failed",
                extra={"error": str(e)},
                exc_info=True
            )
            self.disconnect(websocket)

    async def broadcast_json(self, data: Dict[str, Any]):
        """Broadcast JSON data to all connected clients.

        Args:
            data: Dictionary to broadcast as JSON.
        """
        message = json.dumps(data)
        await self.broadcast(message)


manager = ConnectionManager()
