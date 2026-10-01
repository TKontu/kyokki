"""The plausible-shelf-life bands catalog estimates are checked against (H58).

`spices` is the one case pinned here on its own: the seed row is "Spices & Herbs", and a
fresh herb filed under it (basil, parsley) can genuinely be gone in about a week, unlike a
dried spice. A floor of 30 rejected that true answer as implausible (round 2026-09-30-1).
"""

from app.services.shelf_life_bands import DEFAULT_BAND, PLAUSIBLE_DAYS, band_for


class TestBandFor:
    def test_a_seven_day_spice_estimate_is_plausible(self) -> None:
        """A fresh herb filed under spices is not rejected for being short-lived."""
        low, high = band_for("spices")
        assert low <= 7 <= high

    def test_spices_floor_matches_its_pantry_type_siblings(self) -> None:
        low, _ = band_for("spices")
        assert low == 7

    def test_an_unknown_category_gets_the_loose_default(self) -> None:
        assert band_for("nonexistent-category") == DEFAULT_BAND
        assert band_for(None) == DEFAULT_BAND

    def test_every_band_is_shortest_then_longest(self) -> None:
        for category, (low, high) in PLAUSIBLE_DAYS.items():
            assert low <= high, category
