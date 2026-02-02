# Import all the models, so that Base has them registered before being
# imported by other modules
from app.models.category import Category
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.shopping_list_item import ShoppingListItem
from app.models.store_product_alias import StoreProductAlias
from .base_class import Base

__all__ = ["Base"]
