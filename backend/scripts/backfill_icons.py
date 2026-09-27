"""Draw an icon for every product that has none yet (Q18). The operator runs it after deploy.

New products get their icon drawn when they are created; the products that existed before
Q18 do not, and neither does one whose drawing failed. This draws those, oldest first, one at a
time on the configured `ICON_MODEL`, and prints how each one went. A `pending` older than twice
ICON_TIMEOUT counts too: its job died (a restart mid-queue). A product whose icon the cook set
to the category emoji (`cleared`) is never drawn.

Each product is checked again right before it is drawn, so one the API finished, started, or
the cook cleared since the list was read is skipped. Drawings wait their turn with the API's
on the shared database lock, so running this beside a live server is safe.

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
    """Draw what needs drawing. Returns how many were drawn, failed, and skipped."""
    async with sessions() as db:
        todo = [
            (p.id, str(p.canonical_name), p.icon_status)
            for p in await product_icons.products_to_draw(db, limit)
        ]
    print(f"{len(todo)} product(s) to draw on {settings.ICON_MODEL}")
    counts = {"ready": 0, "failed": 0, "skipped": 0}
    for product_id, name, status in todo:
        if dry_run:
            print(f"  would draw  {name}  ({status or 'never drawn'})")
            continue
        async with sessions() as db:
            wanted = await product_icons.still_needs_drawing(db, product_id)
        if not wanted:
            counts["skipped"] += 1
            print(f"  skipped  {name}  (drawn, being drawn or cleared meanwhile)")
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
            f"{counts['ready']} drawn, {counts['failed']} failed, "
            f"{counts['skipped']} skipped, of {len(todo)}"
        )
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="draw at most this many products")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the products, draw nothing"
    )
    args = parser.parse_args(argv)
    asyncio.run(backfill(args.limit, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
