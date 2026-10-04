"""Re-exports `app.domain.storage`, where the category -> storage map now lives."""

from typing import Any

from app.domain import storage as _domain
from app.domain.storage import (
    CATEGORY_STORAGE,
    StorageType,
    _location_by_storage_type,
    location_for_storage,
    storage_type_for_category,
)

__all__ = [
    "CATEGORY_STORAGE",
    "StorageType",
    "_location_by_storage_type",
    "location_for_storage",
    "storage_type_for_category",
]


def __getattr__(name: str) -> Any:
    """`Location` stays lazy here too (PEP 562): see `app.domain.storage`."""
    if name == "Location":
        return _domain.Location
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
