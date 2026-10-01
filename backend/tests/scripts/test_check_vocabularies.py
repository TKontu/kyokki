"""The backend<->frontend vocabulary pin (H24), plus the category pin (round 2026-09-30-1).

Before this, the only place that pinned every seeded category to a fridge area was a
hand-kept list in a frontend test (`fridge.test.ts`'s `SEEDED`); a new seeded category the
frontend forgot to give an area passed every check here and landed in "Other" unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import check_vocabularies
from scripts.check_vocabularies import _frontend_area_categories, _seeded_category_ids

FRIDGE_TS = """
export interface Area {
  id: AreaId
  label: string
  icon: string
  compartment: 'fridge' | 'freezer' | 'pantry' | 'other'
  categories: string[]
}

export const AREAS: Area[] = [
  { id: 'meat', label: 'Meat & fish', icon: '\U0001f969', compartment: 'fridge', categories: ['meat', 'fish'] },
  // A comment between areas, as the real file has
  {
    id: 'condiments',
    label: 'Sauces & condiments',
    icon: '\U0001f36f',
    compartment: 'pantry',
    categories: ['condiments'],
  },
  { id: 'other', label: 'Other', icon: '\U0001f4e6', compartment: 'other', categories: [] },
]

const BY_CATEGORY = new Map()
"""


class TestFrontendAreaCategories:
    def test_reads_every_categories_array_across_the_whole_block(self) -> None:
        assert _frontend_area_categories(FRIDGE_TS) == {"meat", "fish", "condiments"}

    def test_an_empty_categories_array_contributes_nothing(self) -> None:
        assert "other" not in _frontend_area_categories(FRIDGE_TS)

    def test_none_when_there_is_no_areas_export(self) -> None:
        assert _frontend_area_categories("export const NOTHING = 1\n") is None


class TestSeededCategoryIds:
    def test_reads_the_real_seed_without_importing_it(self) -> None:
        """Regression: importing `app.db.seed_categories` needs Postgres/Redis settings
        this script has no other reason to require (it broke the type-check CI job,
        which has neither configured)."""
        ids = _seeded_category_ids(check_vocabularies.SEED_CATEGORIES_PY)

        assert ids is not None
        assert {"meat", "spices", "condiments"} <= ids

    def test_none_when_there_is_no_seed_categories_list(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.py"
        empty.write_text("SOMETHING_ELSE = []\n", encoding="utf-8")

        assert _seeded_category_ids(empty) is None

    def test_none_when_the_file_is_missing(self, tmp_path: Path) -> None:
        assert _seeded_category_ids(tmp_path / "does-not-exist.py") is None


class TestMain:
    def test_the_real_files_agree(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Regression: today's `fridge.ts` and `seed_categories.py` must already agree."""
        assert check_vocabularies.main() == 0
        assert "backend and frontend agree" in capsys.readouterr().out

    def test_fails_when_a_seeded_category_has_no_frontend_area(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        real = _seeded_category_ids(check_vocabularies.SEED_CATEGORIES_PY) or set()
        monkeypatch.setattr(
            check_vocabularies,
            "_seeded_category_ids",
            lambda path: {*real, "a-category-nobody-added-an-area-for"},
        )

        assert check_vocabularies.main() == 1
        assert "a-category-nobody-added-an-area-for" in capsys.readouterr().out

    def test_fails_clearly_when_fridge_ts_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            check_vocabularies, "FRIDGE_TS", tmp_path / "does-not-exist.ts"
        )

        assert check_vocabularies.main() == 1
        assert "lib/fridge.ts is missing" in capsys.readouterr().out
