"""Generate an icon for every gap product that has none yet (Q18-G2). Run after deploy.

A "gap" product is food, not shown with an exact or cook-chosen emoji, and not `cleared`
(the cook's own "use the category emoji"). New products are generated when they are created;
the ones that existed before Q18-G2 are not, and neither is one whose render failed. This
generates those, oldest first, one at a time through the shared Postgres lock
(`services/product_icons.py`), and prints how each one went. A `pending` older than twice
COMFYUI_TIMEOUT counts too: its job died (a restart mid-queue).

Each candidate gets a library pass first (the repo-shipped icon library, operator ask
2026-10-03, `app.services.icon_library`): a name that matches there is applied with no
render at all, whatever `COMFYUI_BASE_URL` is set to - see `product_icons.apply_library_icon`.
`--dry-run` reports "would apply from library" separately from "would generate", and
`--library-only` applies only what the library covers and needs no ComfyUI.

Each product left over is checked again right before it is generated, so one the API
finished, started, or the cook cleared since the list was read is skipped. Jobs wait their
turn with the API's on the shared database lock, so running this beside a live server is
safe. Refuses to run (beyond listing, and beyond the library pass under `--library-only`)
while `COMFYUI_BASE_URL` is empty - there is nowhere to send the render.

    python -m scripts.backfill_icons --dry-run
    python -m scripts.backfill_icons --limit 20
    python -m scripts.backfill_icons --library-only
    docker compose run --rm kyokki-api python -m scripts.backfill_icons
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.config import settings
from app.crud import product_master as crud_product
from app.models.product_master import IconStatus
from app.services import product_icons

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _default_sessions() -> AbstractAsyncContextManager[AsyncSession]:
    return app_session.AsyncSessionLocal()


async def backfill(
    limit: int | None,
    dry_run: bool,
    sessions: SessionFactory = _default_sessions,
    *,
    library_only: bool = False,
) -> dict[str, int]:
    """Apply the icon library where it matches, then generate what still needs it.

    Returns how many were applied from the `library`, ended `ready`, `failed`, still
    `pending` (still running, or a newer Regenerate from the API raced in first), `gone`
    (the product was deleted mid-job), or were `skipped` (generated, being generated, or
    cleared meanwhile, or - under `--library-only` - simply no library match).

    `--library-only` needs no ComfyUI and ignores `COMFYUI_BASE_URL` entirely; a plain run
    refuses outright (beyond the library pass and `--dry-run`) when it is empty, since
    there would be nowhere to send what the library did not cover.
    """
    counts = {
        "library": 0,
        "ready": 0,
        "failed": 0,
        "pending": 0,
        "gone": 0,
        "skipped": 0,
    }
    if not dry_run and not library_only and not settings.COMFYUI_BASE_URL:
        print("COMFYUI_BASE_URL is empty; generation is disabled. Refusing to run.")
        return counts

    async with sessions() as db:
        todo = [
            (p.id, str(p.canonical_name), p.icon_status)
            for p in await product_icons.products_to_generate(db, limit)
        ]
    print(f"{len(todo)} gap product(s) to generate")
    for product_id, name, status in todo:
        if dry_run:
            if await product_icons.apply_library_icon(product_id, dry_run=True):
                print(f"  would apply from library  {name}")
            else:
                print(f"  would generate  {name}  ({status or 'never generated'})")
            continue
        if await product_icons.apply_library_icon(product_id):
            counts["library"] += 1
            print(f"  library  {name}")
            continue
        if library_only:
            counts["skipped"] += 1
            print(f"  skipped  {name}  (no library match)")
            continue
        async with sessions() as db:
            wanted = await product_icons.still_needs_generation(db, product_id)
        if not wanted:
            counts["skipped"] += 1
            print(
                f"  skipped  {name}  (generated, being generated or cleared meanwhile)"
            )
            continue
        started = time.monotonic()
        await product_icons.draw_icon(product_id)
        async with sessions() as db:
            product = await crud_product.get_icon_subject(db, product_id)
        # F12 review: a non-ready outcome used to be called "failed" across the board, which
        # hid a product deleted mid-job ("gone") and one still mid-render or raced with
        # another writer ("pending", e.g. a second Regenerate from the API arrived first)
        # behind an actual render failure.
        if product is None:
            bucket = "gone"
        elif product.icon_status == IconStatus.READY:
            bucket = "ready"
        elif product.icon_status == IconStatus.PENDING:
            bucket = "pending"
        else:
            bucket = "failed"
        counts[bucket] += 1
        label = "gone" if product is None else str(product.icon_status)
        print(f"  {label:8} {name}  {time.monotonic() - started:.1f}s")
    if not dry_run:
        print(
            f"{counts['library']} from the library, {counts['ready']} generated, "
            f"{counts['failed']} failed, {counts['pending']} still pending, "
            f"{counts['gone']} gone, {counts['skipped']} skipped, of {len(todo)}"
        )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="generate at most this many products")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the gap products, generate nothing"
    )
    parser.add_argument(
        "--library-only",
        action="store_true",
        help="apply the icon library only; never touch ComfyUI",
    )
    args = parser.parse_args(argv)
    asyncio.run(backfill(args.limit, args.dry_run, library_only=args.library_only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
