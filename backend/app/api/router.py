from fastapi import APIRouter

from .endpoints import health, categories, products, inventory, receipts, websockets, shopping

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, tags=["health"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(receipts.router, prefix="/receipts", tags=["receipts"])
api_router.include_router(shopping.router, prefix="/shopping", tags=["shopping"])
api_router.include_router(websockets.router, tags=["websockets"])
