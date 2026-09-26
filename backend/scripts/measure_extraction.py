"""Measure the production extraction prompt against receipt fixtures.

Every prompt edit is measured before it is kept (Q7, Q8 in docs/vLLM_MANUAL_TEST.md): the
model's per-line estimates are fragile, and a change aimed at one field has twice silenced
the others. This runs the real `extract_from_text` with the configured model, the seeded
categories and, by default, an empty catalog - no database - and counts everything the model
returns. Production offers the catalog (`EXTRACTION_OFFERS_CATALOG`, H17), and a catalog block
has silenced the estimates before (Q7), so `--catalog N` offers the first N names of a fixed
20-name warm catalog.

    python -m scripts.measure_extraction --runs 2 --fixture tests/fixtures/receipts/s_kaupat_order.txt
    python -m scripts.measure_extraction --catalog 20 ...
    python -m scripts.measure_extraction --json ...

Model calls run one after another: the gateway serves one request at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.db.seed_categories import SEED_CATEGORIES
from app.services.llm_extractor import (
    CategoryOption,
    build_instructions,
    extract_from_text,
    prefilter_receipt_text,
)

DEFAULT_FIXTURE = "tests/fixtures/receipts/s_kaupat_order.txt"

# Printed-name fragments whose reading is shown line by line (H54's Finnish terms).
WATCH = (
    "TIKKUPERUNAT",
    "RYPÄLE",
    "MONIVITAMIINI",
    "RIISIPIIRAKKA",
    "PIIRAKKA",
    "VALMISRUOKA",
    "ATERIA",
    "MEHU",
    "RUSINA",
)

# A fixed warm catalog for `--catalog N`: generic names a household that shops like the
# S-kaupat fixture would have confirmed, some matching its lines and some not. Fixed so
# that runs on different branches offer the same block.
CATALOG = (
    "Milk",
    "Lactose-free milk",
    "Oat drink",
    "Feta cheese",
    "Cheddar",
    "Bacon",
    "Chicken fillet strips",
    "Ground beef",
    "Eggs",
    "Butter",
    "Tomato",
    "Cucumber",
    "Carrot",
    "Onion",
    "Banana",
    "Apple",
    "Potato",
    "Rye bread",
    "Orange juice",
    "Chips",
)


def categories() -> list[CategoryOption]:
    return [
        CategoryOption(id=str(c["id"]), name=str(c["display_name"]))
        for c in SEED_CATEGORIES
    ]


async def measure(
    text: str, options: list[CategoryOption], catalog: Sequence[str]
) -> dict[str, Any]:
    prompt_chars = len(
        f"{build_instructions(options, catalog)}\n\n"
        f"Receipt:\n{prefilter_receipt_text(text)}"
    )
    started = time.monotonic()
    result = await extract_from_text(text, options, catalog)
    seconds = round(time.monotonic() - started, 1)
    lines = result.lines
    return {
        "prompt_chars": prompt_chars,
        "model_s": seconds,
        "lines": len(lines),
        "generic": sum(1 for x in lines if x.generic_name),
        "category": sum(1 for x in lines if x.category),
        "non_food": sum(1 for x in lines if x.non_food),
        "sl": sum(1 for x in lines if x.shelf_life_days is not None),
        "os": sum(1 for x in lines if x.opened_shelf_life_days is not None),
        "pw": sum(1 for x in lines if x.piece_grams is not None),
        "watch": [
            {
                "n": x.name,
                "g": x.generic_name,
                "c": "household" if x.non_food else x.category,
            }
            for x in lines
            if any(term in x.name.upper() for term in WATCH)
        ],
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--fixture", action="append", dest="fixtures")
    parser.add_argument(
        "--catalog",
        type=int,
        default=0,
        metavar="N",
        help=f"offer the first N of {len(CATALOG)} fixed catalog names (default 0)",
    )
    parser.add_argument("--json", action="store_true", help="print raw numbers as JSON")
    args = parser.parse_args(argv)
    fixtures = args.fixtures or [DEFAULT_FIXTURE]
    options = categories()
    catalog = CATALOG[: max(args.catalog, 0)]
    if catalog and not settings.EXTRACTION_OFFERS_CATALOG:
        parser.error("--catalog needs EXTRACTION_OFFERS_CATALOG on")
    offered = (
        f"{len(catalog)}-name catalog ({', '.join(catalog)})"
        if catalog
        else "empty catalog"
    )

    results: list[dict[str, Any]] = []
    if not args.json:
        print(
            f"model {settings.LLM_MODEL} at {settings.LLM_BASE_URL}, "
            f"reasoning {settings.LLM_REASONING_STRENGTH}, "
            f"{len(options)} seeded categories, {offered}"
        )
    for fixture in fixtures:
        text = Path(fixture).read_text(encoding="utf-8")
        for run in range(1, args.runs + 1):
            row: dict[str, Any] = {
                "fixture": Path(fixture).name,
                "run": run,
                "catalog": len(catalog),
            }
            row.update(await measure(text, options, catalog))
            results.append(row)
            if args.json:
                continue
            print(
                f"\n{row['fixture']} run {run}: prompt {row['prompt_chars']} chars, "
                f"model {row['model_s']} s, lines {row['lines']}, "
                f"generic {row['generic']}, category {row['category']} "
                f"(household {row['non_food']}), sl {row['sl']}, os {row['os']}, "
                f"pw {row['pw']}"
            )
            for w in row["watch"]:
                print(f"  {w['n']} -> {w['g']} ({w['c']})")
    if args.json:
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
