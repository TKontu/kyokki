"""Measure the production extraction prompt against receipt fixtures.

Every prompt edit is measured before it is kept (Q7, Q8 in docs/vLLM_MANUAL_TEST.md): the
model's per-line estimates are fragile, and a change aimed at one field has twice silenced
the others. This runs the real `extract_from_text` with the configured model, the seeded
categories and an empty catalog - no database - and counts everything the model returns.

    python -m scripts.measure_extraction --runs 2 --fixture tests/fixtures/receipts/s_kaupat_order.txt
    python -m scripts.measure_extraction --json ...

Model calls run one after another: the gateway serves one request at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
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


def categories() -> list[CategoryOption]:
    return [
        CategoryOption(id=str(c["id"]), name=str(c["display_name"]))
        for c in SEED_CATEGORIES
    ]


async def measure(text: str, options: list[CategoryOption]) -> dict[str, Any]:
    prompt_chars = len(
        f"{build_instructions(options, ())}\n\nReceipt:\n{prefilter_receipt_text(text)}"
    )
    started = time.monotonic()
    result = await extract_from_text(text, options, ())
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
    parser.add_argument("--json", action="store_true", help="print raw numbers as JSON")
    args = parser.parse_args(argv)
    fixtures = args.fixtures or [DEFAULT_FIXTURE]
    options = categories()

    results: list[dict[str, Any]] = []
    if not args.json:
        print(
            f"model {settings.LLM_MODEL} at {settings.LLM_BASE_URL}, "
            f"reasoning {settings.LLM_REASONING_STRENGTH}, "
            f"{len(options)} seeded categories, empty catalog"
        )
    for fixture in fixtures:
        text = Path(fixture).read_text(encoding="utf-8")
        for run in range(1, args.runs + 1):
            row = {"fixture": Path(fixture).name, "run": run}
            row.update(await measure(text, options))
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
