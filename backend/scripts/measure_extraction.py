"""Measure the production extraction prompt against receipt fixtures.

Every prompt edit is measured before it is kept (Q7, Q8 in docs/vLLM_MANUAL_TEST.md): the
model's per-line estimates are fragile, and a change aimed at one field has twice silenced
the others. This runs the real `extract_from_text` with the configured model, the seeded
categories and, by default, an empty catalog - no database - and counts everything the model
returns. Production offers the catalog (`EXTRACTION_OFFERS_CATALOG`, H17), and a catalog block
has silenced the estimates before (Q7), so `--catalog N` offers the first N names of a fixed
20-name warm catalog, and `--catalog-overlap` a ~200-name warm catalog that holds the
fixtures' own generic names - the case in which a whole receipt lost 9 of 15 lines (Q27).

Completeness (Q27): with an `expected_*.json` beside the fixture, the expected printed names
the model found are counted (exact after `normalize_receipt_name`), for the first read and
after reconciliation - the targeted re-read, printed-line rows and any receipt profile. The
receipt's own arithmetic (line totals against the printed total) is reported too, with
whether the re-read was called and how long the first read took. `--raw-dir DIR` stores the
raw answer of any read whose categories cover less than half of its rows, the "1 of 15
categories" signal, for a look at what the model answered.

    python -m scripts.measure_extraction --runs 2 --fixture tests/fixtures/receipts/s_kaupat_order.txt
    python -m scripts.measure_extraction --catalog 20 ...
    python -m scripts.measure_extraction --catalog-overlap --old-catalog-wording ...
    python -m scripts.measure_extraction --json ...
    python -m scripts.measure_extraction --raw-dir /tmp/raw ...

Model calls run one after another: the gateway serves one request at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.db.seed_categories import SEED_CATEGORIES
from app.parsers.base import ExtractedLine
from app.services import llm_extractor, receipt_processing
from app.services.llm_extractor import (
    CategoryOption,
    LLMExtractionError,
    build_instructions,
    extract_from_text,
    format_numbered,
    number_receipt_lines,
)
from app.services.matching_service import normalize_receipt_name
from app.services.receipt_processing import reconcile_text_read

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

# `--catalog-overlap`: a warm household catalog of ~200 generic names that includes the
# generic names of every fixture's products (K-Citymarket, S-kaupat, the synthetic ones), as
# a catalog grows after months of confirmed receipts. Q27's receipt lost the 9 lines whose
# products were *not* in a catalog like this. Fixed so runs on different branches compare.
OVERLAP_CATALOG = (
    # K-Citymarket fixture
    "Cookie",
    "Ice cream",
    "Grape",
    "Entrecote",
    "Potato",
    "Cherry tomato",
    "Pepper",
    "Egg",
    "Parsnip",
    "Soap",
    "Broccoli",
    "Tampon",
    "Sauerkraut",
    "Hummus",
    # S-kaupat fixture
    "Lactose-free milk",
    "Apple sauce",
    "Mango",
    "Feta cheese",
    "Pomegranate",
    "Cheddar",
    "Taco sauce",
    "Sour cream",
    "Nacho chips",
    "Bacon",
    "Cheese",
    "Oat drink",
    "Compost bag",
    "Trash bag",
    "Rye crisp",
    "French fries",
    "Olive oil",
    "Carrot",
    "Apple",
    "Pear",
    "Laundry vinegar",
    "Liquid soap",
    "Sweet chili dip",
    "Cleaning cloth",
    "Kitchen spray",
    "All-purpose cleaner",
    "Mulled wine",
    "Turkish yoghurt",
    "Red onion",
    "Lettuce",
    "Tomato puree",
    "Multivitamin",
    "Lime",
    "Chicken fillet",
    "Mozzarella",
    "Wheat flour",
    "Parsley",
    "Tomato",
    "Butter",
    "Banana",
    "Multivitamin juice",
    "Cucumber",
    # Croatian and German synthetic fixtures
    "Milk",
    "Bread",
    "Chocolate",
    "Yoghurt",
    "Dish soap",
    "Rye bread",
    # the rest of a household's usual shopping
    "Ground beef",
    "Minced pork",
    "Pork chop",
    "Beef steak",
    "Chicken thigh",
    "Whole chicken",
    "Salmon fillet",
    "Tuna",
    "Shrimp",
    "Fish fingers",
    "Sausage",
    "Frankfurter",
    "Sliced ham",
    "Salami",
    "Meatball",
    "Liver casserole",
    "Blood sausage",
    "Cream",
    "Whipping cream",
    "Cream cheese",
    "Cottage cheese",
    "Quark",
    "Skyr",
    "Buttermilk",
    "Kefir",
    "Emmental",
    "Edam",
    "Gouda",
    "Parmesan",
    "Blue cheese",
    "Halloumi",
    "Brie",
    "Margarine",
    "Oat yoghurt",
    "Soy drink",
    "Almond drink",
    "Orange juice",
    "Apple juice",
    "Grape juice",
    "Coffee",
    "Tea",
    "Cocoa",
    "Mineral water",
    "Soda",
    "Beer",
    "Cider",
    "Wine",
    "Oatmeal",
    "Muesli",
    "Cornflakes",
    "Rice",
    "Pasta",
    "Spaghetti",
    "Macaroni",
    "Noodles",
    "Couscous",
    "Quinoa",
    "Bulgur",
    "Lentil",
    "Chickpea",
    "Kidney bean",
    "Canned tomato",
    "Coconut milk",
    "Ketchup",
    "Mustard",
    "Mayonnaise",
    "Soy sauce",
    "Pesto",
    "Salsa",
    "Honey",
    "Jam",
    "Peanut butter",
    "Nutella",
    "Sugar",
    "Salt",
    "Black pepper",
    "Paprika powder",
    "Cinnamon",
    "Baking powder",
    "Yeast",
    "Vanilla sugar",
    "Rapeseed oil",
    "Vinegar",
    "Crispbread",
    "Toast bread",
    "Baguette",
    "Bun",
    "Karelian pasty",
    "Tortilla",
    "Pita bread",
    "Croissant",
    "Doughnut",
    "Biscuit",
    "Candy",
    "Liquorice",
    "Crisps",
    "Popcorn",
    "Peanut",
    "Almond",
    "Walnut",
    "Raisin",
    "Orange",
    "Lemon",
    "Mandarin",
    "Kiwi",
    "Pineapple",
    "Melon",
    "Watermelon",
    "Strawberry",
    "Blueberry",
    "Raspberry",
    "Lingonberry",
    "Plum",
    "Peach",
    "Avocado",
    "Onion",
    "Garlic",
    "Leek",
    "Spring onion",
    "Cabbage",
    "Cauliflower",
    "Zucchini",
    "Eggplant",
    "Spinach",
    "Rocket",
    "Iceberg lettuce",
    "Celery",
    "Beetroot",
    "Swede",
    "Sweet potato",
    "Mushroom",
    "Corn",
    "Pea",
    "Green bean",
    "Frozen vegetables",
    "Frozen berries",
    "Pizza",
    "Lasagne",
    "Ready meal",
    "Soup",
    "Dumpling",
    "Toilet paper",
    "Paper towel",
    "Dishwasher tablet",
    "Laundry detergent",
    "Fabric softener",
    "Shampoo",
    "Toothpaste",
    "Deodorant",
    "Razor",
    "Diaper",
    "Cat food",
    "Dog food",
    "Aluminium foil",
    "Cling film",
    "Baking paper",
    "Candle",
    "Battery",
)

# The catalog block as it read before Q27, for `--old-catalog-wording`
OLD_CATALOG_BLOCK = (
    "\n  When an equivalent product is listed here, use its name exactly. "
    "Known products: {names}."
)


def categories() -> list[CategoryOption]:
    return [
        CategoryOption(id=str(c["id"]), name=str(c["display_name"]))
        for c in SEED_CATEGORIES
    ]


def expected_for(fixture: Path) -> dict[str, Any] | None:
    """`expected_<stem>.json` beside the fixture (s_kaupat_order -> expected_s_kaupat)."""
    stems = [fixture.stem, fixture.stem.removesuffix("_order")]
    for stem in stems:
        path = fixture.with_name(f"expected_{stem}.json")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def found(
    lines: Sequence[ExtractedLine], expected: dict[str, Any] | None
) -> int | None:
    """Expected printed names that were read, as a multiset, exact after normalising."""
    if expected is None:
        return None
    wanted = Counter(normalize_receipt_name(x["name"]) for x in expected["lines"])
    got = Counter(normalize_receipt_name(x.name) for x in lines)
    return sum((wanted & got).values())


# How many targeted re-reads the reconciliation called in the current measurement
_RE_READS: list[float] = []
# The lines each re-read was asked about, to see why it ran
_RE_READ_LINES: list[list[str]] = []
_extract_unaccounted_lines = receipt_processing.extract_unaccounted_lines


async def _counted_re_read(*args: Any, **kwargs: Any) -> Any:
    started = time.monotonic()
    _RE_READ_LINES.append([f"{n}: {line}" for n, line in args[0]])
    try:
        return await _extract_unaccounted_lines(*args, **kwargs)
    finally:
        _RE_READS.append(round(time.monotonic() - started, 1))


receipt_processing.extract_unaccounted_lines = _counted_re_read  # type: ignore[assignment]


async def measure(
    text: str,
    options: list[CategoryOption],
    catalog: Sequence[str],
    expected: dict[str, Any] | None,
    reconcile: bool,
    raw_dir: Path | None = None,
    label: str = "",
) -> dict[str, Any]:
    numbered = [(n, line) for n, line in number_receipt_lines(text) if n is not None]
    prompt_chars = len(
        f"{build_instructions(options, catalog)}\n\nReceipt:\n{format_numbered(numbered)}"
    )
    started = time.monotonic()
    result = await extract_from_text(text, options, catalog)
    seconds = round(time.monotonic() - started, 1)
    lines = list(result.lines)
    row: dict[str, Any] = {
        "prompt_chars": prompt_chars,
        "model_s": seconds,
        "lines": len(lines),
        "expected": len(expected["lines"]) if expected else None,
        "found": found(lines, expected),
        "generic": sum(1 for x in lines if x.generic_name),
        "category": sum(1 for x in lines if x.category),
        "non_food": sum(1 for x in lines if x.non_food),
        "sl": sum(1 for x in lines if x.shelf_life_days is not None),
        "os": sum(1 for x in lines if x.opened_shelf_life_days is not None),
        "pw": sum(1 for x in lines if x.piece_grams is not None),
        "cited": sum(1 for x in lines if x.source_lines),
        "x": len(result.other_lines),
        "t": result.receipt_total,
        "te": result.tax_exclusive,
        "lc": result.language,
        "cc": result.country,
        "invalid": result.invalid_entries,
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
    if raw_dir is not None and lines and row["category"] < len(lines) / 2:
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{label}.json"
        path.write_text(result.raw_completion or "", encoding="utf-8")
        row["raw_saved"] = str(path)
    if not reconcile:
        return row
    _RE_READS.clear()
    _RE_READ_LINES.clear()
    started = time.monotonic()
    outcome = await reconcile_text_read(text, result, options)
    final = outcome.extraction.lines
    completeness = outcome.completeness or {}
    expected_total = expected.get("total") if expected else None
    row.update(
        reconcile_s=round(time.monotonic() - started, 1),
        after_lines=len(final),
        after_found=found(final, expected),
        after_category=sum(1 for x in final if x.category),
        re_reads=len(_RE_READS),
        re_read_s=sum(_RE_READS),
        re_read_lines=[line for asked in _RE_READ_LINES for line in asked],
        x_lines=[(o.line, o.kind, o.amount) for o in result.other_lines],
        first_prices=[(x.source_lines, x.price) for x in lines],
        retry=completeness.get("recovered_by_retry"),
        raw=completeness.get("recovered_raw_lines"),
        unaccounted=completeness.get("unaccounted_lines"),
        profile=completeness.get("profile"),
        profile_only=completeness.get("profile_only_lines"),
        items_sum=completeness.get("items_sum"),
        expected_total=expected_total,
        note=outcome.note,
        raw_names=[x.name for x in final if x.recovered == "raw_line"],
        missing=sorted(
            (
                Counter(normalize_receipt_name(x["name"]) for x in expected["lines"])
                - Counter(normalize_receipt_name(x.name) for x in final)
            ).elements()
        )
        if expected
        else [],
    )
    return row


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
    parser.add_argument(
        "--catalog-overlap",
        action="store_true",
        help=f"offer the {len(OVERLAP_CATALOG)}-name catalog holding the fixtures' names",
    )
    parser.add_argument(
        "--old-catalog-wording",
        action="store_true",
        help="word the catalog block as it was before Q27",
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help="first read only: no targeted re-read (one model call per run)",
    )
    parser.add_argument("--json", action="store_true", help="print raw numbers as JSON")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help="store the raw answer of a read whose categories cover < half its rows",
    )
    args = parser.parse_args(argv)
    fixtures = args.fixtures or [DEFAULT_FIXTURE]
    options = categories()
    catalog: Sequence[str] = (
        OVERLAP_CATALOG if args.catalog_overlap else CATALOG[: max(args.catalog, 0)]
    )
    if catalog and not settings.EXTRACTION_OFFERS_CATALOG:
        parser.error("--catalog needs EXTRACTION_OFFERS_CATALOG on")
    if args.old_catalog_wording:
        llm_extractor.CATALOG_BLOCK = OLD_CATALOG_BLOCK
    wording = "old" if args.old_catalog_wording else "reworded"
    offered = (
        f"{len(catalog)}-name catalog ({wording} wording)"
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
        path = Path(fixture)
        text = path.read_text(encoding="utf-8")
        expected = expected_for(path)
        for run in range(1, args.runs + 1):
            row: dict[str, Any] = {
                "fixture": path.name,
                "run": run,
                "catalog": len(catalog),
                "wording": wording,
            }
            started = time.monotonic()
            try:
                row.update(
                    await measure(
                        text,
                        options,
                        catalog,
                        expected,
                        not args.no_reconcile,
                        args.raw_dir,
                        f"{path.stem}-{len(catalog)}-{wording}-run{run}",
                    )
                )
            except LLMExtractionError as exc:
                # A failed read is a result too (a timeout is what production sees)
                row.update(error=str(exc), model_s=round(time.monotonic() - started, 1))
                results.append(row)
                if not args.json:
                    print(f"\n{row['fixture']} run {run}: FAILED {exc}")
                continue
            results.append(row)
            if args.json:
                continue
            print(
                f"\n{row['fixture']} run {run}: prompt {row['prompt_chars']} chars, "
                f"model {row['model_s']} s, lines {row['lines']}, "
                f"found {row['found']}/{row['expected']}, "
                f"generic {row['generic']}, category {row['category']} "
                f"(household {row['non_food']}), sl {row['sl']}, os {row['os']}, "
                f"pw {row['pw']}, cited {row['cited']}, x {row['x']}, t {row['t']}, "
                f"te {row['te']}, lc {row['lc']}, cc {row['cc']}, "
                f"invalid {row['invalid']}"
            )
            if row.get("raw_saved"):
                print(
                    f"  categories under half the rows: raw answer {row['raw_saved']}"
                )
            if "after_lines" in row:
                print(
                    f"  after reconciliation ({row['reconcile_s']} s): lines "
                    f"{row['after_lines']}, found {row['after_found']}/{row['expected']}, "
                    f"category {row['after_category']}, unaccounted {row['unaccounted']}, "
                    f"re-reads {row['re_reads']} ({row['re_read_s']} s), "
                    f"recovered {row['retry']}, raw {row['raw']}, profile {row['profile']} "
                    f"(+{row['profile_only']}), sum {row['items_sum']} vs total "
                    f"{row['t']} (expected {row['expected_total']})"
                )
                if row["raw_names"] or row["missing"]:
                    print(f"  raw rows {row['raw_names']}, missing {row['missing']}")
                if row["note"]:
                    print(f"  note: {row['note']}")
            for w in row["watch"]:
                print(f"  {w['n']} -> {w['g']} ({w['c']})")
    if args.json:
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
