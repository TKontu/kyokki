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


def test_readme_exit_table_matches_help() -> None:
    from pathlib import Path

    from kyokki.cli import EXIT_CODES

    meanings: dict[str, str] = {}
    last = ""
    for line in EXIT_CODES.splitlines()[1:]:
        if line.startswith("    "):
            meanings[last] += " " + line.strip()
        else:
            last, _, text = line.strip().partition(" ")
            meanings[last] = text
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    for code, text in meanings.items():
        assert f"| {code} | {text} |" in readme


def test_consume_help_says_no_candidates_is_not_found() -> None:
    text = " ".join(render(HELP_PAGES["stock-consume"]).split())
    assert "the candidates are printed and the exit code is 4" in text
    assert "matches nothing, the exit code is 3" in text


@pytest.mark.parametrize("name", HELP_PAGES.keys())
def test_help_documents_invalid_and_uses_the_lan_port(name: str) -> None:
    text = render(HELP_PAGES[name])
    assert "400 invalid" in text
    assert ":8000" not in text


@pytest.mark.parametrize(
    "name", ["stock-list", "stock-add", "stock-consume", "product-name-add"]
)
def test_help_describes_units_and_locations(name: str) -> None:
    text = render(HELP_PAGES[name])
    if name in ("stock-add", "stock-consume"):
        assert "dl, tsp, tbsp, g, pcs" in text
    if name != "product-name-add":
        assert "main_fridge" in text


def test_shopping_add_help_describes_units_and_priorities() -> None:
    text = " ".join(render(HELP_PAGES["shopping-add"]).split())
    assert "dl, tsp, tbsp, g, pcs" in text
    assert "urgent" in text and "normal" in text and "low" in text
    assert "default: 1 pcs" in text


@pytest.mark.parametrize(
    "name",
    [
        "shopping-add",
        "shopping-done",
        "shopping-remove",
        "shopping-generate",
    ],
)
def test_shopping_mutation_help_offers_the_idempotency_key(name: str) -> None:
    assert "--idempotency-key" in render(HELP_PAGES[name])


def test_readme_lists_every_shopping_command() -> None:
    from pathlib import Path

    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    for command in ("list", "add", "done", "remove", "generate", "export"):
        assert f"`kyokki shopping {command}" in readme
