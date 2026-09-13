# Import all the models so that Base.metadata has every table registered before
# Alembic (alembic/env.py) or create_all() reads it. Without the models import,
# autogenerate compares the database against an empty schema.
from app import models  # noqa: F401

from .base_class import Base

__all__ = ["Base"]
