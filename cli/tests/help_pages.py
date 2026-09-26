"""The -h pages with a golden snapshot, and how to render one.

Shared by the golden test and ``regen_golden.py``.
"""

import contextlib
import io
import os
from pathlib import Path

from kyokki import cli

GOLDEN = Path(__file__).parent / "golden"

HELP_PAGES: dict[str, list[str]] = {
    "kyokki": ["-h"],
    "doctor": ["doctor", "-h"],
    "stock": ["stock", "-h"],
    "stock-list": ["stock", "list", "-h"],
    "stock-add": ["stock", "add", "-h"],
    "stock-consume": ["stock", "consume", "-h"],
    "product": ["product", "-h"],
    "product-resolve": ["product", "resolve", "-h"],
    "product-name": ["product", "name", "-h"],
    "product-name-add": ["product", "name", "add", "-h"],
    "category": ["category", "-h"],
    "category-list": ["category", "list", "-h"],
}


def render(argv: list[str]) -> str:
    """The help text at a fixed 80 columns, whatever the terminal."""
    saved = os.environ.get("COLUMNS")
    os.environ["COLUMNS"] = "80"
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = cli.main(argv)
    finally:
        if saved is None:
            del os.environ["COLUMNS"]
        else:
            os.environ["COLUMNS"] = saved
    assert code == 0, f"{argv} exited {code}"
    return buffer.getvalue()


def golden_path(name: str) -> Path:
    return GOLDEN / f"{name}.txt"
