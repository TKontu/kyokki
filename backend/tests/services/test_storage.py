"""Category → storage type → location defaults."""

import pytest

from app.db.seed_categories import SEED_CATEGORIES
from app.services.storage import location_for_storage, storage_type_for_category


class TestStorageTypeForCategory:
    @pytest.mark.parametrize(
        ("category", "expected"),
        [
            ("frozen", "freezer"),
            ("pantry", "pantry"),
            ("condiments", "pantry"),
            ("snacks", "pantry"),
            ("beverages", "pantry"),
            ("bread", "pantry"),
            ("meat", "refrigerator"),
            ("fish", "refrigerator"),
            ("dairy", "refrigerator"),
            ("cheese", "refrigerator"),
            ("produce", "refrigerator"),
            ("fruits", "refrigerator"),
        ],
    )
    def test_seeded_categories(self, category, expected):
        assert storage_type_for_category(category) == expected

    def test_every_seeded_category_is_mapped_explicitly(self):
        from app.services.storage import CATEGORY_STORAGE

        assert {c["id"] for c in SEED_CATEGORIES} == set(CATEGORY_STORAGE)

    @pytest.mark.parametrize("category", [None, "", "household", "seafood"])
    def test_unknown_or_missing_defaults_to_refrigerator(self, category):
        assert storage_type_for_category(category) == "refrigerator"


class TestLocationForStorage:
    @pytest.mark.parametrize(
        ("storage", "location"),
        [
            ("refrigerator", "main_fridge"),
            ("freezer", "freezer"),
            ("pantry", "pantry"),
            (None, "main_fridge"),
            ("garage", "main_fridge"),
        ],
    )
    def test_maps_storage_to_location(self, storage, location):
        assert location_for_storage(storage) == location
