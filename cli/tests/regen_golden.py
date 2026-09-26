"""Rewrite the golden -h snapshots after a deliberate help change.

    python cli/tests/regen_golden.py

The tests only compare; this is the one place that writes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from help_pages import GOLDEN, HELP_PAGES, golden_path, render  # noqa: E402


def main() -> None:
    GOLDEN.mkdir(exist_ok=True)
    for name, argv in HELP_PAGES.items():
        path = golden_path(name)
        path.write_text(render(argv), encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
