"""Export good generated icons from a deployment into the repo's icon library.

Operator request (2026-10-03): "migrate the generated icons to the actual repo as
canonical symbols." Today every deployment must render its own icons on a GPU
(`services/product_icons.py`), and the good ones exist only in that deployment's own
database. This script closes the gap in the other direction from
`services/icon_library.py`'s loader: it reads a deployment's products through its own API
- **GET only, nothing here ever mutates the deployment** - picks the ones worth keeping,
and writes `app/resources/icon_library/<slug>.png` plus a matching `index.json` entry, so
a later deployment with the same product name gets the icon instantly, no GPU.

A product is eligible when its generated icon is actually showing: `icon_status` is
`ready`, its emoji is not an exact or cook win (`icon_library`'s whole point is a gap
product with no emoji; the tile would not show the icon otherwise), and `icon_seed` is
not null - the one signal a render, not a library icon already applied by that same
deployment, produced the image (`crud.product_master.store_library_icon` always leaves it
NULL; see `docs/icon_library/README.md`). Non-food is never separately checked here: it
never gets a generated icon in the first place (`product_icons.py`'s own gate), so a
`ready` generated image already implies food.

A contact sheet (`docs/icon_library/contact_sheet.png`, grid, name under each icon) is
written alongside the index for every export with at least one PNG written - that sheet,
plus the diff, is the operator's review in the PR; a bad one is deleted there along with
its `index.json` line (`docs/icon_library/README.md`).

    python -m scripts.export_icon_library --api http://192.168.0.136:17300 --all-ready --dry-run
    python -m scripts.export_icon_library --api http://192.168.0.136:17300 --all-ready
    python -m scripts.export_icon_library --api http://192.168.0.136:17300 --names "Quark,Leek"
    python -m scripts.export_icon_library --api http://192.168.0.136:17300 --all-ready --replace
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.domain.product_names import normalize_product_name
from app.services.icon_briefs import brief_for
from app.services.icon_library import index_entry, slug_for
from app.services.icon_subjects import subject_for

BACKEND_DIR = Path(__file__).resolve().parent.parent
LIBRARY_DIR = BACKEND_DIR / "app" / "resources" / "icon_library"
INDEX_PATH = LIBRARY_DIR / "index.json"
CONTACT_SHEET_PATH = BACKEND_DIR.parent / "docs" / "icon_library" / "contact_sheet.png"

# The emoji wins the tile and this export must leave alone (`lib/productIcon.ts`'s own
# precedence; `icon_library`'s whole point is a gap product with no such win).
EMOJI_WINS = {"exact", "cook"}

REQUEST_TIMEOUT = 30.0


@dataclass
class ExportResult:
    """What one run found and did, for the CLI to print and the tests to assert on."""

    lines: list[str] = field(default_factory=list)
    eligible: int = 0
    exported: int = 0
    replaced: int = 0
    skipped_existing: int = 0


def _is_eligible(
    product: dict[str, Any], *, names: set[str] | None, all_ready: bool
) -> bool:
    """Whether this API product is a candidate at all - before the "already in the
    library" check, which `export()` does separately so `--replace` can still reach it.
    """
    if product.get("icon_status") != "ready":
        return False
    if product.get("emoji_match") in EMOJI_WINS:
        return False
    if product.get("icon_seed") is None:
        return False
    name = str(product.get("canonical_name") or "")
    if not name:
        return False
    if names is not None:
        return normalize_product_name(name) in names
    return all_ready


def load_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    """The library's current index, or `{}` for a missing or unreadable one."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_index(index: dict[str, Any], path: Path = INDEX_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _contact_sheet(
    entries: list[tuple[str, bytes]], path: Path = CONTACT_SHEET_PATH
) -> None:
    """A grid of every exported icon, its name under it - the operator's review sheet."""
    if not entries:
        return
    cell_w, cell_h, icon_size = 140, 170, 120
    columns = min(6, len(entries))
    rows = (len(entries) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (name, data) in enumerate(entries):
        row, column = divmod(index, columns)
        x, y = column * cell_w, row * cell_h
        with Image.open(io.BytesIO(data)) as icon:
            resized = icon.convert("RGBA").resize((icon_size, icon_size))
            sheet.paste(resized, (x + (cell_w - icon_size) // 2, y + 8), resized)
        label = name if len(name) <= 18 else f"{name[:15]}..."
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        draw.text(
            (x + (cell_w - text_width) // 2, y + icon_size + 12),
            label,
            fill=(0, 0, 0, 255),
            font=font,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path, format="PNG")


async def fetch_products(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/api/products")
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


async def fetch_icon(client: httpx.AsyncClient, product_id: str) -> bytes:
    response = await client.get(f"/api/products/{product_id}/icon.png")
    response.raise_for_status()
    return response.content


async def export(
    api: str,
    *,
    names: list[str] | None = None,
    all_ready: bool = False,
    replace: bool = False,
    dry_run: bool = False,
    library_dir: Path = LIBRARY_DIR,
    index_path: Path | None = None,
    contact_sheet_path: Path = CONTACT_SHEET_PATH,
    http_client: httpx.AsyncClient | None = None,
) -> ExportResult:
    """List, pick, and (unless `dry_run`) download and write. GET only, always - this
    never sends the deployment a POST, PATCH or DELETE, whatever the flags ask for.

    Returns the result for both the CLI (prints `result.lines`) and tests (asserts on the
    counts) - never prints anything itself.
    """
    if index_path is None:
        index_path = library_dir / "index.json"
    name_filter = (
        {normalize_product_name(n) for n in names} if names is not None else None
    )

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(base_url=api, timeout=REQUEST_TIMEOUT)
    result = ExportResult()
    try:
        products = await fetch_products(client)
        index = load_index(index_path)
        exported_images: list[tuple[str, bytes]] = []

        for product in products:
            if not _is_eligible(product, names=name_filter, all_ready=all_ready):
                continue
            result.eligible += 1
            name = str(product["canonical_name"])
            key = normalize_product_name(name)
            already_in_library = key in index
            if already_in_library and not replace:
                result.skipped_existing += 1
                result.lines.append(f"skip (already in library)  {name}")
                continue
            if dry_run:
                result.lines.append(f"would export  {name}")
                continue

            image = await fetch_icon(client, str(product["id"]))
            file_name = f"{slug_for(name)}.png"
            library_dir.mkdir(parents=True, exist_ok=True)
            (library_dir / file_name).write_bytes(image)
            subject = product.get("subject") or brief_for(name) or subject_for(name)
            index[key] = index_entry(
                name,
                image,
                source=f"generated:{urlparse(api).netloc}",
                seed=product.get("icon_seed"),
                subject=subject,
            )
            exported_images.append((name, image))
            if already_in_library:
                result.replaced += 1
                result.lines.append(f"replaced  {name}")
            else:
                result.exported += 1
                result.lines.append(f"exported  {name}")

        if not dry_run and exported_images:
            save_index(index, index_path)
            _contact_sheet(
                sorted(exported_images, key=lambda entry: entry[0]), contact_sheet_path
            )
        return result
    finally:
        if owns_client:
            await client.aclose()


def _parse_names(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [name.strip() for name in value.split(",") if name.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--api",
        required=True,
        help="the deployment's base URL, e.g. http://192.168.0.136:17300",
    )
    parser.add_argument(
        "--names", help="comma-separated product names to export (default: none)"
    )
    parser.add_argument(
        "--all-ready",
        action="store_true",
        help="export every eligible ready product, not just --names",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="overwrite a library entry that already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what would be exported; write nothing",
    )
    args = parser.parse_args(argv)

    names = _parse_names(args.names)
    if names is None and not args.all_ready:
        print("nothing to export: pass --names or --all-ready")
        return 0

    result = asyncio.run(
        export(
            args.api,
            names=names,
            all_ready=args.all_ready,
            replace=args.replace,
            dry_run=args.dry_run,
        )
    )
    for line in result.lines:
        print(f"  {line}")
    print(
        f"{result.eligible} eligible, {result.exported} exported, "
        f"{result.replaced} replaced, {result.skipped_existing} already in the library"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
