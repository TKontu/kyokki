"""The old `app.services.*` paths still serve every name, as the same objects (A2).

The code moved to `app.domain` and `app.crud.product_name`; the services modules are
re-exports. Each name some importer took from the old path at the time of the move is
listed here, so a shim that drops one fails a test rather than an importer at runtime.
"""

from __future__ import annotations

import importlib

import pytest

from app.schemas.inventory_item import StorageLocation

REEXPORTS = {
    ("app.services.units", "app.domain.units"): [
        "canonical_factor",
        "grams_from_name",
        "grams_to_pieces",
        "pieces_to_grams",
        "quantise",
        "receipt_line_quantity",
        "to_canonical",
        "to_canonical_decimal",
        "unit_type_for",
        "CanonicalUnit",
        "UnitType",
    ],
    ("app.services.item_status", "app.domain.item_status"): [
        "DISCARDED",
        "ItemEvent",
        "ItemFrozen",
        "PARTIAL_THRESHOLD",
        "is_frozen",
        "next_status",
        "opens_the_pack",
    ],
    ("app.services.storage", "app.domain.storage"): [
        "CATEGORY_STORAGE",
        "StorageType",
        "location_for_storage",
        "storage_type_for_category",
    ],
    ("app.services.product_names", "app.domain.product_names"): [
        "normalize_product_name",
    ],
    ("app.services.product_names", "app.crud.product_name"): [
        "CanonicalName",
        "KnownName",
        "UnknownName",
        "forget_product_name",
        "known_names",
        "learn_product_name",
        "names_for_product",
        "product_for_name",
    ],
}

CASES = [(old, new, name) for (old, new), names in REEXPORTS.items() for name in names]


@pytest.mark.parametrize(("old", "new", "name"), CASES)
def test_old_path_serves_the_moved_object(old: str, new: str, name: str) -> None:
    assert getattr(importlib.import_module(old), name) is getattr(
        importlib.import_module(new), name
    )


def test_storage_location_alias_still_resolves_from_both_paths() -> None:
    from app.domain import storage as domain_storage
    from app.services import storage as services_storage

    assert domain_storage.Location is StorageLocation
    assert services_storage.Location is StorageLocation
    with pytest.raises(AttributeError):
        _ = services_storage.NoSuchName  # type: ignore[attr-defined]
