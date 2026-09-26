"""Every -h matches its golden snapshot and carries examples and the exit codes."""

import pytest
from help_pages import HELP_PAGES, golden_path, render


@pytest.mark.parametrize("name", HELP_PAGES.keys())
def test_help_matches_golden(name: str) -> None:
    path = golden_path(name)
    assert path.exists(), f"missing {path}; run cli/tests/regen_golden.py"
    assert render(HELP_PAGES[name]) == path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", HELP_PAGES.keys())
def test_help_has_examples_and_exit_codes(name: str) -> None:
    text = render(HELP_PAGES[name])
    assert "examples:" in text
    assert text.count("\n  kyokki ") >= 2, "at least two examples"
    assert "exit codes:" in text
    for code in range(8):
        assert f"\n  {code} " in text


@pytest.mark.parametrize(
    "name", ["stock-list", "stock-add", "stock-consume", "product-name-add"]
)
def test_help_describes_units_and_locations(name: str) -> None:
    text = render(HELP_PAGES[name])
    if name in ("stock-add", "stock-consume"):
        assert "dl, tsp, tbsp, g, pcs" in text
    if name != "product-name-add":
        assert "main_fridge" in text
