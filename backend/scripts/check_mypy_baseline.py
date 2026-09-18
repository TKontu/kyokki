"""Fail on *new* mypy errors, not on the ones already here.

`pyproject.toml` sets `strict = true` and the code is not there yet, so CI ran mypy
with `continue-on-error: true` and the count was free to grow. This keys the known
errors on file plus error code - never on line numbers, which churn on every edit -
so a refactor that moves code does not show up as a regression.

    python -m scripts.check_mypy_baseline            # check
    python -m scripts.check_mypy_baseline --update   # accept the current state

H21 takes the baseline to zero and deletes this.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
BASELINE = BACKEND_ROOT / "mypy-baseline.txt"
TARGET = "app"

# e.g. "app\api\endpoints\receipts.py:196: error: Argument 1 ...  [arg-type]"
ERROR_LINE = re.compile(r"^(?P<path>.+?):\d+: error: .*\[(?P<code>[a-z-]+)\]\s*$")


def run_mypy() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", TARGET],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"mypy could not run (exit {result.returncode})")
    return result.stdout


def counts(output: str) -> Counter[str]:
    found: Counter[str] = Counter()
    for line in output.splitlines():
        match = ERROR_LINE.match(line.strip())
        if match:
            path = match["path"].replace("\\", "/")
            found[f"{path}\t{match['code']}"] += 1
    return found


def read_baseline() -> Counter[str]:
    if not BASELINE.exists():
        return Counter()
    known: Counter[str] = Counter()
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        count, path, code = line.split("\t")
        known[f"{path}\t{code}"] = int(count)
    return known


def write_baseline(found: Counter[str]) -> None:
    lines = [
        "# Known mypy errors, keyed on file and error code (never line numbers).",
        "# Regenerate with: python -m scripts.check_mypy_baseline --update",
        "# Adding to this file needs a reason; H21 empties it.",
    ]
    lines += [f"{found[key]}\t{key}" for key in sorted(found)]
    # newline="\n" so regenerating on Windows and on CI produces the same bytes.
    with BASELINE.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline from the current run",
    )
    args = parser.parse_args()

    found = counts(run_mypy())

    if args.update:
        write_baseline(found)
        print(f"baseline written: {sum(found.values())} errors in {len(found)} places")
        return 0

    known = read_baseline()
    regressions = sorted(
        (key, found[key], known.get(key, 0))
        for key in found
        if found[key] > known.get(key, 0)
    )

    if regressions:
        print("New mypy errors (file, code, now, allowed):", file=sys.stderr)
        for key, now, allowed in regressions:
            path, code = key.split("\t")
            print(f"  {path}  [{code}]  {now} > {allowed}", file=sys.stderr)
        print(
            "\nFix them, or run --update with a reason if they are genuinely expected.",
            file=sys.stderr,
        )
        return 1

    total, allowed = sum(found.values()), sum(known.values())
    fixed = allowed - total
    print(
        f"mypy: {total} known errors, none new" + (f" ({fixed} fixed)" if fixed else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
