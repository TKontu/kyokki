"""Apply the curated emoji table to the existing catalog (Q18 build).

New products get their emoji looked up, or a proposal scheduled, when they are created
(`app/services/product_emoji.py`, hooked next to the icon drawing); the products that existed
before this build do not. This walks the whole catalog once and applies the curated table
(`app/resources/emoji_curated.json`) and the learned table (confirmed proposals) with no model
call at all, printing what would change or what changed. Non-food, `cook` and `cleared`
products are never touched - a hand-set choice, or one the cook cleared, is never overwritten.

`--propose` also asks the model, in batches of `--batch-size` (20 by default) and one
request at a time, for the names neither table knows - exactly as `scripts/emoji_trial.py`
does; its `exact` answers land as `proposed`, shown on the products page's review list until
a person confirms them, the same as a new product's own miss would be. Each batch is applied
(or, on `--dry-run`, reported) as soon as it answers, so a run interrupted partway through a
large catalog keeps the batches it finished.

The operator runs this inside the `kyokki-api` container after deploy:

    python -m scripts.backfill_emoji --dry-run
    python -m scripts.backfill_emoji
    python -m scripts.backfill_emoji --propose
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
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

# Matches scripts/emoji_trial.py's own default; one request per batch, one batch at a time.
DEFAULT_BATCH_SIZE = 20


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


async def plan(db: AsyncSession) -> tuple[list[Change], list[ProductMaster]]:
    """The curated table's changes, and every miss it left for `propose_in_batches`.

    No model call here: a miss is only collected, never asked about, so a plain
    (non-`--propose`) run never reaches the gateway.
    """
    changes: list[Change] = []
    misses: list[ProductMaster] = []
    for product in await _candidates(db):
        name = str(product.canonical_name)
        if await product_emoji.is_non_food(db, name):
            continue
        hit = await product_emoji.lookup(db, name)
        if hit is None:
            misses.append(product)
            continue
        emoji, match = hit
        already = (
            product.emoji or None
        ) == emoji and product.emoji_match == match.value
        if already:
            continue
        changes.append(Change(product.id, name, product.emoji_match, emoji, match))
    return changes, misses


async def propose_in_batches(
    misses: list[ProductMaster],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_batch: Callable[[list[Change]], Awaitable[None]] | None = None,
) -> list[Change]:
    """Ask the model about every miss, one batch after another (the gateway serves one
    request at a time) - exactly as `scripts/emoji_trial.py` does.

    `on_batch` gets each batch's changes as soon as it answers, so a caller can apply or
    print them right away: an interrupted run then keeps the batches it finished, rather
    than losing the whole `--propose` pass to one failure near the end.
    """
    changes: list[Change] = []
    for start in range(0, len(misses), batch_size):
        batch = misses[start : start + batch_size]
        answers = await product_emoji.propose([str(p.canonical_name) for p in batch])
        if answers is None:
            continue
        batch_changes = [
            Change(p.id, str(p.canonical_name), p.emoji_match, a.emoji, a.match)
            for p, a in zip(batch, answers, strict=True)
        ]
        changes.extend(batch_changes)
        if on_batch:
            await on_batch(batch_changes)
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


def _report(changes: list[Change], *, dry_run: bool, label: str) -> None:
    print(f"{len(changes)} product(s) would change from the {label}")
    for change in changes:
        before = change.before or "never looked up"
        verb = "would set" if dry_run else "set"
        print(
            f"  {verb}  {change.name}  {before} -> {_describe(change.match, change.emoji)}"
        )


async def _apply_and_report(
    changes: list[Change], *, dry_run: bool, label: str, sessions: SessionFactory
) -> None:
    """Report a batch (or the curated-table pass), and apply it right away unless dry-run -
    so a later batch failing never undoes what an earlier one already wrote."""
    _report(changes, dry_run=dry_run, label=label)
    if not dry_run and changes:
        async with sessions() as db:
            applied = await apply_changes(db, changes)
        print(f"  {applied} applied")


async def backfill(
    *,
    dry_run: bool,
    propose: bool,
    batch_size: int = DEFAULT_BATCH_SIZE,
    sessions: SessionFactory = _default_sessions,
) -> list[Change]:
    """The curated table's changes first, applied (or reported) at once; then, with
    `propose`, the model's answer for every miss, one batch at a time, each one applied (or
    reported) as soon as it comes back. Returns everything planned, table and model alike.
    """
    async with sessions() as db:
        changes, misses = await plan(db)

    await _apply_and_report(
        changes, dry_run=dry_run, label="curated table", sessions=sessions
    )

    if propose and misses:
        print(
            f"{len(misses)} miss(es); asking the model in batches of {batch_size}, "
            "one request at a time"
        )

        async def on_batch(batch_changes: list[Change]) -> None:
            await _apply_and_report(
                batch_changes, dry_run=dry_run, label="model", sessions=sessions
            )

        proposed = await propose_in_batches(
            misses, batch_size=batch_size, on_batch=on_batch
        )
        changes.extend(proposed)
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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="model proposal batch size (default 20)",
    )
    args = parser.parse_args(argv)
    asyncio.run(
        backfill(dry_run=args.dry_run, propose=args.propose, batch_size=args.batch_size)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
