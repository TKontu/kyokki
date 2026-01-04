from fastapi import APIRouter

from .endpoints import health

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, tags=["health"])
