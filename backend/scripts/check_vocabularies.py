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

from app.models.product_master import ShelfLifeSource
from app.models.product_name import NameSource
from app.schemas.consumption_log import ConsumptionAction
from app.schemas.inventory_item import ExpirySource, InventoryStatus, StorageLocation
from app.schemas.receipt import ReceiptStatus

FRONTEND_TYPES = Path(__file__).resolve().parents[2] / "frontend" / "types"

#: python enum -> (TypeScript file, exported type name)
PAIRS: list[tuple[type[StrEnum], str, str]] = [
    (InventoryStatus, "inventory.ts", "InventoryItemStatus"),
    (StorageLocation, "inventory.ts", "InventoryLocation"),
    (ExpirySource, "inventory.ts", "ExpirySource"),
    (ShelfLifeSource, "product.ts", "ShelfLifeSource"),
    (NameSource, "product.ts", "NameSource"),
    (ReceiptStatus, "receipt.ts", "ReceiptStatus"),
    (ConsumptionAction, "consumption.ts", "ConsumptionAction"),
]

_MEMBER = re.compile(r"'([^']+)'")


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

    if problems:
        print("Vocabularies have drifted between the backend and the iPad:\n")
        for problem in problems:
            print(f"  {problem}")
        print(
            "\nAdd the value on both sides. `frontend/types/` mirrors `backend/app/schemas/` "
            "by hand;\nthis check is what makes forgetting it a failure rather than a surprise."
        )
        return 1

    print(f"vocabularies: {len(PAIRS)} checked, backend and frontend agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
