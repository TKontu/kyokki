"""Where products are kept by default: category → storage type → inventory location."""

from typing import Literal

StorageType = Literal["refrigerator", "freezer", "pantry"]
Location = Literal["main_fridge", "freezer", "pantry"]

# Every seeded category id (app/db/seed_categories.py) is listed explicitly.
CATEGORY_STORAGE: dict[str, StorageType] = {
    "meat": "refrigerator",
    "fish": "refrigerator",
    "dairy": "refrigerator",
    "cheese": "refrigerator",
    "produce": "refrigerator",
    "fruits": "refrigerator",
    "bread": "pantry",
    "frozen": "freezer",
    "pantry": "pantry",
    "beverages": "pantry",
    "condiments": "pantry",
    "snacks": "pantry",
}

_STORAGE_LOCATION: dict[str, Location] = {
    "refrigerator": "main_fridge",
    "freezer": "freezer",
    "pantry": "pantry",
}


def storage_type_for_category(category_id: str | None) -> StorageType:
    """Default storage for a category; unknown or missing categories go to the fridge.

    The fridge is the safe default for food, and the review screen lets the user move it.
    """
    return CATEGORY_STORAGE.get(category_id or "", "refrigerator")


def location_for_storage(storage_type: str | None) -> Location:
    return _STORAGE_LOCATION.get(storage_type or "", "main_fridge")
