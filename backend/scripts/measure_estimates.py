"""Measure the catalog estimate prompt against a fixed list of generic products (Q19).

The estimate writes a shelf life into every product it answers for, and those numbers date
the food in the fridge. So a change to `catalog_estimates.INSTRUCTIONS` is measured before it
is kept, the same rule the extraction prompt lives by (Q7, Q8 in docs/vLLM_MANUAL_TEST.md).

This runs the real `estimate_shelf_lives` with the configured model and no database, prints
one row per product, and counts the answers that were dropped - as out of band (a number its
category could not mean) or as missing. Products with a `gate` in the fixture are checked
against it; the operator's anchors are the gated ones.

    python -m scripts.measure_estimates
    python -m scripts.measure_estimates --fixture tests/fixtures/shelf_life/estimate_products.json
    python -m scripts.measure_estimates --json

Exits 1 when a gate fails or an answer is dropped as out of band, so a run can be scripted.
Model calls run one after another: the gateway serves one request at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.catalog_estimates import (
    EstimateRequest,
    band_for,
    estimate_shelf_lives,
)

DEFAULT_FIXTURE = "tests/fixtures/shelf_life/estimate_products.json"

# The message `parse_estimates` logs for an answer outside its category's band.
OUT_OF_BAND = "Ignoring an implausible shelf life"


class _DropCounter(logging.Handler):
    """Counts the answers `parse_estimates` threw away as implausible."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.dropped: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == OUT_OF_BAND:
            self.dropped.append(
                {
                    "product": getattr(record, "product", None),
                    "answered": getattr(record, "answered", None),
                }
            )


def load_fixture(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    products = data["products"] if isinstance(data, dict) else data
    return list(products)


def within(days: int | None, gate: list[int | None] | None) -> bool | None:
    """True/False against the gate, None when the product has no gate."""
    if not gate:
        return None
    if days is None:
        return False
    low, high = gate
    return (low is None or days >= low) and (high is None or days <= high)


async def measure(products: list[dict[str, Any]]) -> dict[str, Any]:
    counter = _DropCounter()
    logger = logging.getLogger("app.services.catalog_estimates")
    logger.addHandler(counter)
    started = time.monotonic()
    try:
        estimates = await estimate_shelf_lives(
            [
                EstimateRequest(id=p["id"], name=p["name"], category=p["category"])
                for p in products
            ]
        )
    finally:
        logger.removeHandler(counter)
    seconds = round(time.monotonic() - started, 1)

    by_id = {e.id: e for e in estimates}
    rows = []
    for product in products:
        estimate = by_id.get(product["id"])
        days = estimate.shelf_life_days if estimate else None
        rows.append(
            {
                "id": product["id"],
                "name": product["name"],
                "category": product["category"],
                "band": list(band_for(product["category"])),
                "d": days,
                "o": estimate.opened_shelf_life_days if estimate else None,
                "gate": product.get("gate"),
                "pass": within(days, product.get("gate")),
            }
        )
    return {
        "model": settings.LLM_MODEL,
        "seconds": seconds,
        "asked": len(products),
        "answered": len(estimates),
        "dropped_out_of_band": counter.dropped,
        "missing": len(products) - len(estimates) - len(counter.dropped),
        "rows": rows,
    }


def _show(value: Any) -> str:
    return "-" if value is None else str(value)


def print_report(result: dict[str, Any]) -> None:
    print(
        f"model {result['model']}  {result['seconds']} s  "
        f"answered {result['answered']} of {result['asked']}"
    )
    print(f"{'product':40} {'category':10} {'d':>5} {'o':>5}  gate")
    for row in result["rows"]:
        gate = row["gate"]
        verdict = ""
        if gate:
            span = f"{gate[0]}+" if gate[1] is None else f"{gate[0]}-{gate[1]}"
            verdict = f"{span} " + ("pass" if row["pass"] else "FAIL")
        print(
            f"{row['name'][:40]:40} {row['category']:10} "
            f"{_show(row['d']):>5} {_show(row['o']):>5}  {verdict}"
        )
    dropped = result["dropped_out_of_band"]
    print(f"dropped as out of band: {len(dropped)}  missing: {result['missing']}")
    for drop in dropped:
        print(f"  {drop['product']}: {drop['answered']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--json", action="store_true", help="print JSON instead")
    args = parser.parse_args(argv)

    result = asyncio.run(measure(load_fixture(Path(args.fixture))))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    failed = [row for row in result["rows"] if row["pass"] is False]
    return 1 if failed or result["dropped_out_of_band"] else 0


if __name__ == "__main__":
    sys.exit(main())
