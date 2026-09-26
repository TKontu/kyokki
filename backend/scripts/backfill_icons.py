"""Draw an icon for every product that has none yet (Q18). The operator runs it after deploy.

New products get their icon drawn when they are created; the products that existed before
Q18 do not, and neither does one whose drawing failed. This queues those, oldest first, one at
a time on the configured `ICON_MODEL`, and prints how each one went. A product whose icon the
cook set to the category emoji (`cleared`) is never drawn, and neither is one being drawn now
(`pending`); redraw either from the product editor.

    python -m scripts.backfill_icons --dry-run
    python -m scripts.backfill_icons --limit 20
    docker compose run --rm kyokki-api python -m scripts.backfill_icons

Model calls run one after another: the gateway serves one request at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.config import settings
from app.models.product_master import IconStatus, ProductMaster
from app.services.product_icons import draw_icon


async def products_to_draw(
    db: AsyncSession, limit: int | None = None
) -> list[tuple[UUID, str, str | None]]:
    """(id, name, status) of each product without a drawing to show, oldest first."""
    query = (
        select(
            ProductMaster.id, ProductMaster.canonical_name, ProductMaster.icon_status
        )
        .where(
            or_(
                ProductMaster.icon_status.is_(None),
                ProductMaster.icon_status == IconStatus.FAILED,
            )
        )
        .order_by(ProductMaster.created_at, ProductMaster.id)
    )
    if limit is not None:
        query = query.limit(limit)
    return [(row[0], row[1], row[2]) for row in (await db.execute(query)).all()]


async def backfill(limit: int | None, dry_run: bool) -> int:
    async with app_session.AsyncSessionLocal() as db:
        todo = await products_to_draw(db, limit)
    print(f"{len(todo)} product(s) to draw on {settings.ICON_MODEL}")
    ready = 0
    for product_id, name, status in todo:
        if dry_run:
            print(f"  would draw  {name}  ({status or 'never drawn'})")
            continue
        started = time.monotonic()
        await draw_icon(product_id)
        async with app_session.AsyncSessionLocal() as db:
            after = await db.scalar(
                select(ProductMaster.icon_status).where(ProductMaster.id == product_id)
            )
        ready += after == IconStatus.READY
        print(f"  {after or 'gone':8} {name}  {time.monotonic() - started:.1f}s")
    if not dry_run:
        print(f"{ready} of {len(todo)} drawn")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="draw at most this many products")
    parser.add_argument(
        "--dry-run", action="store_true", help="list the products, draw nothing"
    )
    args = parser.parse_args(argv)
    return asyncio.run(backfill(args.limit, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
