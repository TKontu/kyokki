# Import all the models, so that Base has them registered before being
# imported by other modules
from .base_class import Base

__all__ = ["Base"]
