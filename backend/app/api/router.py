from fastapi import APIRouter

from .endpoints import (
    categories,
    consumption_log,
    events,
    ha,
    health,
    icon_library,
    inventory,
    product_audit,
    products,
    receipts,
    scanner,
    shopping,
    stock,
    websockets,
)

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, tags=["health"])
api_router.include_router(categories.router, prefix="/categories", tags=["categories"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(
    icon_library.router, prefix="/icon-library", tags=["icon-library"]
)
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(stock.router, prefix="/stock", tags=["stock"])
api_router.include_router(receipts.router, prefix="/receipts", tags=["receipts"])
api_router.include_router(shopping.router, prefix="/shopping", tags=["shopping"])
api_router.include_router(
    consumption_log.router, prefix="/consumption-log", tags=["consumption-log"]
)
api_router.include_router(scanner.router, prefix="/scanner", tags=["scanner"])
api_router.include_router(websockets.router, tags=["websockets"])
api_router.include_router(events.router, tags=["events"])
api_router.include_router(ha.router, prefix="/ha", tags=["ha"])
api_router.include_router(product_audit.router, prefix="/audit", tags=["audit"])
