"""Pydantic schemas for API request/response validation."""

from app.schemas.category import (
    CategoryBase,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from app.schemas.consumption_log import (
    ConsumptionLogBase,
    ConsumptionLogCreate,
    ConsumptionLogResponse,
    ConsumptionLogUpdate,
)
from app.schemas.inventory_item import (
    InventoryItemBase,
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
)
from app.schemas.product_master import (
    ProductMasterBase,
    ProductMasterCreate,
    ProductMasterResponse,
    ProductMasterUpdate,
)
from app.schemas.receipt import (
    ReceiptBase,
    ReceiptCreate,
    ReceiptResponse,
    ReceiptUpdate,
)
from app.schemas.shopping_list_item import (
    ShoppingListItemBase,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingListItemUpdate,
)
from app.schemas.store_product_alias import (
    StoreProductAliasBase,
    StoreProductAliasCreate,
    StoreProductAliasResponse,
    StoreProductAliasUpdate,
)

__all__ = [
    # Category
    "CategoryBase",
    "CategoryCreate",
    "CategoryUpdate",
    "CategoryResponse",
    # Product Master
    "ProductMasterBase",
    "ProductMasterCreate",
    "ProductMasterUpdate",
    "ProductMasterResponse",
    # Store Product Alias
    "StoreProductAliasBase",
    "StoreProductAliasCreate",
    "StoreProductAliasUpdate",
    "StoreProductAliasResponse",
    # Receipt
    "ReceiptBase",
    "ReceiptCreate",
    "ReceiptUpdate",
    "ReceiptResponse",
    # Inventory Item
    "InventoryItemBase",
    "InventoryItemCreate",
    "InventoryItemUpdate",
    "InventoryItemResponse",
    # Consumption Log
    "ConsumptionLogBase",
    "ConsumptionLogCreate",
    "ConsumptionLogUpdate",
    "ConsumptionLogResponse",
    # Shopping List Item
    "ShoppingListItemBase",
    "ShoppingListItemCreate",
    "ShoppingListItemUpdate",
    "ShoppingListItemResponse",
]
