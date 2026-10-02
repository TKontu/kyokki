"""Propose a Finnish display name for the existing catalog (Post-MVP frontier item 13).

A new product gets its Finnish name proposed when it is created
(`app/services/shelf_life_on_create.py`, hooked next to the icon drawing and the exact emoji
lookup); the products that existed before this lane do not. This walks the whole catalog once,
proposing a name for every product with no `fi` entry yet, in batches of `--batch-size` (20 by
default) and one request at a time - the gateway serves one request at a time
(`app/services/llm_http.py`). A cook-set name is never touched: a product already carrying any
`fi` row, cook or model, is skipped.

Each batch is applied (or, on `--dry-run`, reported) as soon as it answers, so a run
interrupted partway through a large catalog keeps the batches it finished - the same shape as
`scripts/backfill_emoji.py --propose`.

The operator runs this inside the `kyokki-api` container after deploy:

    python -m scripts.backfill_display_names --dry-run
    python -m scripts.backfill_display_names
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.crud import product_master as crud_product
from app.models.product_master import ProductMaster
from app.services.display_names import propose_finnish_names

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# Matches `scripts/backfill_emoji.py`'s own default; one request per batch, one batch at a time.
DEFAULT_BATCH_SIZE = 20

LANGUAGE = "fi"


def _default_sessions() -> AbstractAsyncContextManager[AsyncSession]:
    return app_session.AsyncSessionLocal()


@dataclass(frozen=True)
class Change:
    id: UUID
    name: str
    display_name: str


async def candidates(db: AsyncSession) -> list[ProductMaster]:
    """Every product with no Finnish display name yet, cook's or model's."""
    products = (
        (await db.execute(select(ProductMaster).order_by(ProductMaster.canonical_name)))
        .scalars()
        .all()
    )
    return [p for p in products if LANGUAGE not in p.display_names]


def _report(changes: list[Change], *, dry_run: bool) -> None:
    print(f"{len(changes)} product(s) would get a Finnish name")
    verb = "would propose" if dry_run else "proposed"
    for change in changes:
        print(f"  {verb}  {change.name} -> {change.display_name}")


async def _apply_and_report(
    changes: list[Change], *, dry_run: bool, sessions: SessionFactory
) -> None:
    """Report a batch, and apply it right away unless dry-run - so a later batch failing
    never undoes what an earlier one already wrote."""
    _report(changes, dry_run=dry_run)
    if not dry_run and changes:
        async with sessions() as db:
            applied = await apply_changes(db, changes)
        print(f"  {applied} applied")


async def propose_in_batches(
    products: list[ProductMaster],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_batch: Callable[[list[Change]], Awaitable[None]] | None = None,
) -> list[Change]:
    """Ask the model about every candidate, one batch after another - exactly as
    `scripts/backfill_emoji.py --propose` does. `on_batch` gets each batch's changes as
    soon as it answers, so a caller can apply or print them right away.
    """
    changes: list[Change] = []
    for start in range(0, len(products), batch_size):
        batch = products[start : start + batch_size]
        answers = await propose_finnish_names([str(p.canonical_name) for p in batch])
        if answers is None:
            continue
        batch_changes = [
            Change(p.id, str(p.canonical_name), name)
            for p, name in zip(batch, answers, strict=True)
            if name
        ]
        changes.extend(batch_changes)
        if on_batch:
            await on_batch(batch_changes)
    return changes


async def apply_changes(db: AsyncSession, changes: list[Change]) -> int:
    """Write every planned change, skipping any product the cook (or an earlier run)
    already gave a Finnish name meanwhile. Returns how many were applied."""
    applied = 0
    for change in changes:
        product = await crud_product.get_display_name_subject(db, change.id)
        if product is None or LANGUAGE in product.display_names:
            continue
        await crud_product.set_display_name(
            db, product, language=LANGUAGE, name=change.display_name, source="model"
        )
        await db.commit()
        applied += 1
    return applied


async def backfill(
    *,
    dry_run: bool,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sessions: SessionFactory = _default_sessions,
) -> list[Change]:
    """Propose a Finnish name for every product that has none, one batch at a time, each one
    applied (or, on `--dry-run`, reported) as soon as it comes back."""
    async with sessions() as db:
        products = await candidates(db)

    if not products:
        print("Nothing to propose: every product already has a Finnish name.")
        return []

    print(
        f"{len(products)} product(s) with no Finnish name; asking the model in "
        f"batches of {batch_size}, one request at a time"
    )

    async def on_batch(batch_changes: list[Change]) -> None:
        await _apply_and_report(batch_changes, dry_run=dry_run, sessions=sessions)

    return await propose_in_batches(products, batch_size=batch_size, on_batch=on_batch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the proposals, write nothing"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="model proposal batch size (default 20)",
    )
    args = parser.parse_args(argv)
    asyncio.run(backfill(dry_run=args.dry_run, batch_size=args.batch_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
