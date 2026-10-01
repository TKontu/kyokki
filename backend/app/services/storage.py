"""Where products are kept by default: category → storage type → inventory location.

No top-level import from `app.schemas` (round 2026-09-30-1): both `app.schemas.category`
and `app.schemas.receipt` import from this module at their own module scope, and
`app.schemas` (the package `__init__`) imports both of them - so if this module's own
top-level code needed `app.schemas.inventory_item` (for `StorageLocation`), the very first
import of `app.services.storage` (as happened running `tests/services/test_storage.py`
alone) would run the `app.schemas` package `__init__`, which reaches back into this module
while it is still mid-import and finds `location_for_storage`/`StorageType` not yet
defined - an ImportError cycle. `StorageLocation` is only ever needed once something calls
`location_for_storage` or reads `Location`, by which time normal import order has always
finished loading `app.schemas`, so both are resolved lazily instead.
"""

from functools import cache
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.schemas.inventory_item import StorageLocation

StorageType = Literal["refrigerator", "freezer", "pantry"]

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
    "spices": "pantry",
    "snacks": "pantry",
}


def storage_type_for_category(category_id: str | None) -> StorageType:
    """Default storage for a category; unknown or missing categories go to the fridge.

    The fridge is the safe default for food, and the review screen lets the user move it.
    """
    return CATEGORY_STORAGE.get(category_id or "", "refrigerator")


@cache
def _location_by_storage_type() -> dict[str, "StorageLocation"]:
    from app.schemas.inventory_item import StorageLocation

    return {
        "refrigerator": StorageLocation.MAIN_FRIDGE,
        "freezer": StorageLocation.FREEZER,
        "pantry": StorageLocation.PANTRY,
    }


def location_for_storage(storage_type: str | None) -> "StorageLocation":
    table = _location_by_storage_type()
    return table.get(storage_type or "", table["refrigerator"])


def __getattr__(name: str) -> Any:
    """Resolves `Location` lazily (PEP 562): see the module docstring.

    #: Kept as an alias so callers need not import from `schemas`; it is the same
    #: vocabulary. It used to be a third spelling of it, alongside a `Literal` on the
    #: schema and a free `str` on create (H24).
    """
    if name == "Location":
        from app.schemas.inventory_item import StorageLocation

        return StorageLocation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
