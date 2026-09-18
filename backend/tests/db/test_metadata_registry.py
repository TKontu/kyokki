"""The Alembic metadata source must know every model table."""

from app.db.base import Base
from app.models import __all__ as model_names


def test_base_metadata_registers_every_model_table() -> None:
    """alembic/env.py uses app.db.base.Base; an empty registry makes autogenerate
    propose dropping every table (this happened before MVP-F2)."""
    tables = set(Base.metadata.tables)
    expected = {
        "category",
        "product_master",
        "store_product_alias",
        "receipt",
        "inventory_item",
        "consumption_log",
        "shopping_list_item",
        "non_food_name",
        "product_name",
    }
    assert expected <= tables, f"missing tables: {expected - tables}"
    assert len(model_names) == len(expected)
