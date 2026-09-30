"""Fail when a backend vocabulary and its TypeScript twin disagree (H24).

`frontend/types/` mirrors `backend/app/schemas/` by hand. Nothing checked it, so a value added
on one side reached the other only when somebody remembered - and in one month four fields
(`pack_grams`, `shelf_life_source`, `items_redated`, `frozen`) were hand-copied across, each
time noticed only because an unrelated test fixture stopped compiling.

This compares the *members* of the closed vocabularies. It deliberately does not compare whole
interfaces: `Vocabulary<T>` exists so the iPad can render a value this build has never heard of
(H04), and the shapes drift for good reasons. A vocabulary is different - both sides have to
agree on what the legal values are, or a create call the API accepts is one the screen cannot.

    python -m scripts.check_vocabularies

Shopping's `priority` and `source` are absent on purpose: there is no shopping UI, so there is
no TypeScript to disagree with. Add them here when there is.
"""

from __future__ import annotations

import re
import sys
from enum import StrEnum
from pathlib import Path

from app.db.seed_categories import SEED_CATEGORIES
from app.models.product_master import IconStatus, ShelfLifeSource
from app.models.product_name import NameSource
from app.schemas.consumption_log import ConsumptionAction
from app.schemas.inventory_item import ExpirySource, InventoryStatus, StorageLocation
from app.schemas.receipt import ReceiptStatus

FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
FRONTEND_TYPES = FRONTEND_ROOT / "types"
#: The only backend<->frontend category pin (round 2026-09-30-1): `AREAS` in `fridge.ts`
#: files every seeded category into an area, or it silently lands in "Other".
FRIDGE_TS = FRONTEND_ROOT / "lib" / "fridge.ts"

#: python enum -> (TypeScript file, exported type name)
PAIRS: list[tuple[type[StrEnum], str, str]] = [
    (InventoryStatus, "inventory.ts", "InventoryItemStatus"),
    (StorageLocation, "inventory.ts", "InventoryLocation"),
    (ExpirySource, "inventory.ts", "ExpirySource"),
    (ShelfLifeSource, "product.ts", "ShelfLifeSource"),
    (IconStatus, "product.ts", "IconStatus"),
    (NameSource, "product.ts", "NameSource"),
    (ReceiptStatus, "receipt.ts", "ReceiptStatus"),
    (ConsumptionAction, "consumption.ts", "ConsumptionAction"),
]

_MEMBER = re.compile(r"'([^']+)'")
_AREAS_BLOCK = re.compile(r"export const AREAS: Area\[\] = \[(.+?)\n\]\n", re.DOTALL)
_CATEGORIES_ARRAY = re.compile(r"categories:\s*\[([^\]]*)\]")


def _typescript_members(source: str, name: str) -> set[str] | None:
    """The string literals of `export type <name> = 'a' | 'b'`, across line breaks."""
    match = re.search(
        rf"export type {re.escape(name)}\s*=\s*(.+?)(?:\n\s*\n|\nexport |\n//|\Z)",
        source,
        re.DOTALL,
    )
    if match is None:
        return None
    return set(_MEMBER.findall(match.group(1)))


def _frontend_area_categories(source: str) -> set[str] | None:
    """Every category id a fridge area claims, across all of `AREAS` in `fridge.ts`.

    Not a closed vocabulary like `PAIRS` above - `fridge.ts` has no `export type` to parse -
    so this reads `categories: [...]` inside each area literal instead.
    """
    block = _AREAS_BLOCK.search(source)
    if block is None:
        return None
    covered: set[str] = set()
    for array in _CATEGORIES_ARRAY.finditer(block.group(1)):
        covered.update(_MEMBER.findall(array.group(1)))
    return covered


def main() -> int:
    problems: list[str] = []

    for enum, filename, ts_name in PAIRS:
        path = FRONTEND_TYPES / filename
        if not path.exists():
            problems.append(f"{filename} is missing; {ts_name} cannot be checked")
            continue

        theirs = _typescript_members(path.read_text(encoding="utf-8"), ts_name)
        if theirs is None:
            problems.append(f"{filename} has no `export type {ts_name}`")
            continue

        ours = {member.value for member in enum}
        if ours == theirs:
            continue

        missing = sorted(ours - theirs)
        extra = sorted(theirs - ours)
        detail = []
        if missing:
            detail.append(f"missing from TypeScript: {', '.join(missing)}")
        if extra:
            detail.append(f"not in {enum.__name__}: {', '.join(extra)}")
        problems.append(
            f"{enum.__name__} vs {filename}:{ts_name} - {'; '.join(detail)}"
        )

    seeded = {category["id"] for category in SEED_CATEGORIES}
    if not FRIDGE_TS.exists():
        problems.append("lib/fridge.ts is missing; category coverage cannot be checked")
    else:
        covered = _frontend_area_categories(FRIDGE_TS.read_text(encoding="utf-8"))
        if covered is None:
            problems.append("lib/fridge.ts has no `export const AREAS: Area[]`")
        else:
            uncovered = sorted(seeded - covered)
            if uncovered:
                problems.append(
                    "seed_categories.py has categories no fridge area claims, so they land "
                    f"in Other: {', '.join(uncovered)}"
                )

    if problems:
        print("Vocabularies have drifted between the backend and the iPad:\n")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nAdd the value on both sides. `frontend/types/` mirrors `backend/app/schemas/` "
            "by hand;\nthis check is what makes forgetting it a failure rather than a surprise."
        )
        return 1

    print(
        f"vocabularies: {len(PAIRS)} checked, {len(seeded)} categories covered, "
        "backend and frontend agree"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
