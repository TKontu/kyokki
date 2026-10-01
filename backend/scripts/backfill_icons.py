"""Generate an icon for every gap product that has none yet (Q18-G2). Run after deploy.

A "gap" product is food, not shown with an exact or cook-chosen emoji, and not `cleared`
(the cook's own "use the category emoji"). New products are generated when they are created;
the ones that existed before Q18-G2 are not, and neither is one whose render failed. This
generates those, oldest first, one at a time through the shared Postgres lock
(`services/product_icons.py`), and prints how each one went. A `pending` older than twice
COMFYUI_TIMEOUT counts too: its job died (a restart mid-queue).

Each product is checked again right before it is generated, so one the API finished, started,
or the cook cleared since the list was read is skipped. Jobs wait their turn with the API's on
the shared database lock, so running this beside a live server is safe. Refuses to run (beyond
listing) while `COMFYUI_BASE_URL` is empty - there is nowhere to send the render.

    python -m scripts.backfill_icons --dry-run
    python -m scripts.backfill_icons --limit 20
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
) -> dict[str, int]:
    """Generate what needs generating. Returns how many were generated, failed, skipped."""
    if not dry_run and not settings.COMFYUI_BASE_URL:
        print("COMFYUI_BASE_URL is empty; generation is disabled. Refusing to run.")
        return {"ready": 0, "failed": 0, "skipped": 0}

    async with sessions() as db:
        todo = [
            (p.id, str(p.canonical_name), p.icon_status)
            for p in await product_icons.products_to_generate(db, limit)
        ]
    print(f"{len(todo)} gap product(s) to generate")
    counts = {"ready": 0, "failed": 0, "skipped": 0}
    for product_id, name, status in todo:
        if dry_run:
            print(f"  would generate  {name}  ({status or 'never generated'})")
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
        after = None if product is None else product.icon_status
        counts["ready" if after == IconStatus.READY else "failed"] += 1
        print(f"  {after or 'gone':8} {name}  {time.monotonic() - started:.1f}s")
    if not dry_run:
        print(
            f"{counts['ready']} generated, {counts['failed']} failed, "
            f"{counts['skipped']} skipped, of {len(todo)}"
        )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="generate at most this many products")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the gap products, generate nothing"
    )
    args = parser.parse_args(argv)
    asyncio.run(backfill(args.limit, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
