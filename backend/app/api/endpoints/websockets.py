"""WebSocket endpoint for real-time updates."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websockets import manager
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for receiving real-time updates.

    Clients connect to this endpoint to receive:
    - Receipt processing status updates
    - Inventory item changes (create, update, consume, delete)

    Message format:
    {
        "type": "receipt_status" | "inventory_update",
        "timestamp": "ISO-8601 timestamp",
        "entity_id": "UUID of entity",
        "data": { ... type-specific payload ... }
    }
    """
    await manager.connect(websocket)

    try:
        logger.info("websocket_client_connected")

        # Keep connection alive and handle incoming messages
        while True:
            # Receive messages (for potential future client-to-server communication)
            data = await websocket.receive_text()
            logger.debug("websocket_message_received", extra={"data": data})

            # Currently, we only broadcast server-to-client
            # Future: could implement ping/pong or client commands here

    except WebSocketDisconnect:
        logger.info("websocket_client_disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(
            "websocket_error",
            extra={"error": str(e)},
            exc_info=True
        )
        manager.disconnect(websocket)
