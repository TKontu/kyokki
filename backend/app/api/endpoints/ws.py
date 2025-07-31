from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websockets import manager

router = APIRouter()

@router.websocket("/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
