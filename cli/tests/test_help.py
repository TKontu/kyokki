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
        "shopping-generate",
    ],
)
def test_shopping_mutation_help_offers_the_idempotency_key(name: str) -> None:
    assert "--idempotency-key" in render(HELP_PAGES[name])


def test_shopping_remove_help_is_honest_about_retries() -> None:
    text = " ".join(render(HELP_PAGES["shopping-remove"]).split())
    assert "--idempotency-key" not in text
    assert "ignores Idempotency-Key" in text
    assert "already removed" in text and "exit 3" in text


def test_shopping_export_help_says_a_redirect_writes_the_text() -> None:
    text = " ".join(render(HELP_PAGES["shopping-export"]).split())
    assert "> list.md" in text
    assert "only with --json" in text


def test_shopping_list_help_says_it_pages() -> None:
    text = " ".join(render(HELP_PAGES["shopping-list"]).split())
    assert "every item" in text and "500" in text


def test_shopping_generate_help_keeps_the_backend_rule() -> None:
    text = " ".join(render(HELP_PAGES["shopping-generate"]).split())
    assert "its reorder amount, or the shortfall when it has no reorder amount" in text


def test_shopping_add_help_says_a_linked_product_needs_an_amount() -> None:
    text = " ".join(render(HELP_PAGES["shopping-add"]).split())
    assert "--product-id needs AMOUNT UNIT" in text
    assert "without --product-id" in text


def test_shopping_add_help_does_not_mention_a_kitchen_display() -> None:
    assert "kitchen display" not in render(HELP_PAGES["shopping-add"])


SHOPPING_PAGES = [name for name in HELP_PAGES if name.startswith("shopping")]


@pytest.mark.parametrize("name", SHOPPING_PAGES)
def test_shopping_exit_codes_speak_of_shopping(name: str) -> None:
    text = " ".join(render(HELP_PAGES[name]).split("exit codes:")[1].split())
    assert "nothing matches the name" not in text
    assert "the name belongs to another product" not in text
    assert "the candidates are printed" not in text


@pytest.mark.parametrize(
    ("name", "absent"),
    [
        ("shopping-list", [3, 4, 5, 6]),
        ("shopping-export", [3, 4, 5, 6]),
        ("shopping-generate", [3, 4, 5]),
        ("shopping-done", [4, 5]),
        ("shopping-remove", [4, 5, 6]),
        ("shopping-add", [4, 5]),
    ],
)
def test_shopping_pages_mark_the_codes_that_cannot_occur(
    name: str, absent: list[int]
) -> None:
    table = render(HELP_PAGES[name]).split("exit codes:")[1]
    for code in range(8):
        line = " ".join(table.split(f"\n  {code} ")[1].split("\n  ")[0].split())
        assert ("does not occur" in line) == (code in absent), (code, line)


def test_shopping_export_exit_1_speaks_of_text() -> None:
    table = " ".join(
        render(HELP_PAGES["shopping-export"]).split("exit codes:")[1].split()
    )
    assert "text/plain or text/markdown" in table
    assert "change sent" not in table


def test_readme_lists_every_shopping_command() -> None:
    from pathlib import Path

    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    for command in ("list", "add", "done", "remove", "generate", "export"):
        assert f"`kyokki shopping {command}" in readme
