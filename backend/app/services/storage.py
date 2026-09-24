"""Where products are kept by default: category → storage type → inventory location."""

from typing import Literal

from app.schemas.inventory_item import StorageLocation

StorageType = Literal["refrigerator", "freezer", "pantry"]

#: Kept as an alias so callers need not import from `schemas`; it is the same vocabulary.
#: It used to be a third spelling of it, alongside a `Literal` on the schema and a free
#: `str` on create (H24).
Location = StorageLocation

# Every seeded category id (app/db/seed_categories.py) is listed explicitly.
CATEGORY_STORAGE: dict[str, StorageType] = {
    "meat": "refrigerator",
    "fish": "refrigerator",
    "dairy": "refrigerator",
    "cheese": "refrigerator",
    "produce": "refrigerator",
    "fruits": "refrigerator",
    "bread": "pantry",
    "ready_meals": "refrigerator",
    "frozen": "freezer",
    "pantry": "pantry",
    "beverages": "pantry",
    "condiments": "pantry",
    "snacks": "pantry",
}

_STORAGE_LOCATION: dict[str, StorageLocation] = {
    "refrigerator": StorageLocation.MAIN_FRIDGE,
    "freezer": StorageLocation.FREEZER,
    "pantry": StorageLocation.PANTRY,
}


def storage_type_for_category(category_id: str | None) -> StorageType:
    """Default storage for a category; unknown or missing categories go to the fridge.

    The fridge is the safe default for food, and the review screen lets the user move it.
    """
    return CATEGORY_STORAGE.get(category_id or "", "refrigerator")


def location_for_storage(storage_type: str | None) -> StorageLocation:
    return _STORAGE_LOCATION.get(storage_type or "", StorageLocation.MAIN_FRIDGE)
