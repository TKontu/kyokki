# Import all the models, so that Base has them registered before being
# imported by other modules
from .base_class import Base
from app.models.item import Item
from app.models.product import Product
