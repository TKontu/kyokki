from fastapi import APIRouter
from .endpoints import health, items, ws

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(items.router, prefix="/items", tags=["items"])
api_router.include_router(ws.router, prefix="/ws", tags=["websockets"])
