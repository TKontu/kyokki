"""Apply the curated emoji table to the existing catalog (Q18 build).

New products get their emoji looked up, or a proposal scheduled, when they are created
(`app/services/product_emoji.py`, hooked next to the icon drawing); the products that existed
before this build do not. This walks the whole catalog once and applies the curated table
(`app/resources/emoji_curated.json`) and the learned table (confirmed proposals) with no model
call at all, printing what would change or what changed. Non-food, `cook` and `cleared`
products are never touched - a hand-set choice, or one the cook cleared, is never overwritten.

`--propose` also asks the model, batched and one request at a time, for the names neither
table knows; its `exact` answers land as `proposed`, shown on the products page's review list
until a person confirms them, exactly as a new product's own miss would be.

The operator runs this inside the `kyokki-api` container after deploy:

    python -m scripts.backfill_emoji --dry-run
    python -m scripts.backfill_emoji
    python -m scripts.backfill_emoji --propose
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.crud import product_master as crud_product
from app.models.product_master import EmojiMatch, ProductMaster
from app.services import product_emoji

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# Never touched: a hand-set choice, or one the cook cleared, outlives any backfill.
UNTOUCHABLE = {EmojiMatch.COOK.value, EmojiMatch.CLEARED.value}


def _default_sessions() -> AbstractAsyncContextManager[AsyncSession]:
    return app_session.AsyncSessionLocal()


@dataclass(frozen=True)
class Change:
    id: UUID
    name: str
    before: str | None  # the emoji_match before this backfill, for the printout
    emoji: str | None
    match: EmojiMatch


async def _candidates(db: AsyncSession) -> list[ProductMaster]:
    """Every product the backfill may touch: never `cook` or `cleared`."""
    result = await db.execute(
        select(ProductMaster)
        .where(
            or_(
                ProductMaster.emoji_match.is_(None),
                ProductMaster.emoji_match.notin_(UNTOUCHABLE),
            )
        )
        .order_by(ProductMaster.canonical_name)
    )
    return list(result.scalars().all())


async def plan(db: AsyncSession, *, propose: bool) -> list[Change]:
    """What the backfill would change. With `propose`, also the model's answer for a miss."""
    changes: list[Change] = []
    misses: list[ProductMaster] = []
    for product in await _candidates(db):
        name = str(product.canonical_name)
        if await product_emoji.is_non_food(db, name):
            continue
        hit = await product_emoji.lookup(db, name)
        if hit is None:
            if propose:
                misses.append(product)
            continue
        emoji, match = hit
        already = (
            product.emoji or None
        ) == emoji and product.emoji_match == match.value
        if already:
            continue
        changes.append(Change(product.id, name, product.emoji_match, emoji, match))

    if misses:
        answers = await product_emoji.propose([str(p.canonical_name) for p in misses])
        if answers is not None:
            for product, answer in zip(misses, answers, strict=True):
                changes.append(
                    Change(
                        product.id,
                        str(product.canonical_name),
                        product.emoji_match,
                        answer.emoji,
                        answer.match,
                    )
                )
    return changes


async def apply_changes(db: AsyncSession, changes: list[Change]) -> int:
    """Write every planned change, skipping any the cook has settled meanwhile.

    Returns how many were applied.
    """
    applied = 0
    for change in changes:
        product = await db.get(ProductMaster, change.id)
        if product is None or product.emoji_match in UNTOUCHABLE:
            continue
        await crud_product.set_emoji(
            db, product, emoji=change.emoji, match=change.match
        )
        applied += 1
    return applied


def _describe(match: EmojiMatch, emoji: str | None) -> str:
    return f"{emoji} ({match.value})" if emoji else f"none ({match.value})"


async def backfill(
    *, dry_run: bool, propose: bool, sessions: SessionFactory = _default_sessions
) -> list[Change]:
    """Plan, print, and - unless `dry_run` - apply. Returns the plan either way."""
    async with sessions() as db:
        changes = await plan(db, propose=propose)

    label = "model" if propose else "curated table"
    print(f"{len(changes)} product(s) would change from the {label}")
    for change in changes:
        before = change.before or "never looked up"
        verb = "would set" if dry_run else "set"
        print(
            f"  {verb}  {change.name}  {before} -> {_describe(change.match, change.emoji)}"
        )

    if not dry_run and changes:
        async with sessions() as db:
            applied = await apply_changes(db, changes)
        print(f"{applied} applied")
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="print the changes, write nothing"
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="also ask the model, batched, for names neither table knows",
    )
    args = parser.parse_args(argv)
    asyncio.run(backfill(dry_run=args.dry_run, propose=args.propose))
    return 0


if __name__ == "__main__":
    sys.exit(main())
