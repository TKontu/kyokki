"""Re-key chain keys an OCR misread invented, onto what they resolve to today (Q37 follow-up).

Before `store_chain.normalize_store_chain` grew a fuzzy pass, a misread header such as "Lidi
Suomi Ky" became its own one-off chain key (``lidi-suomi-ky``) instead of ``lidl``. Store
aliases and non-food names are scoped by chain, so everything learned from that receipt is
filed under a chain no other Lidl receipt will ever have again, and the receipt row itself
carries the bad key too.

This lists every distinct chain key the ``receipt``, ``store_product_alias`` and
``non_food_name`` tables hold, what `normalize_store_chain` would map each one to today, how
many rows of each table that key covers, and *how* it would be re-keyed: `exact` means the
stored key, hyphens read back as spaces, now matches a chain pattern exactly - which is
unexpected for something that was stored as a slug in the first place (a flea market literally
named "... sale" reads as an exact match on the `SALE` pattern, for instance) and is flagged
`suspicious` rather than treated the same as a genuine fix. `fuzzy` means the fuzzy pass found a
one-edit-away chain word: the OCR-misread case this script exists for.

``--apply`` takes the specific old keys to rewrite (after reviewing the plan below) and refuses
any name that is not a changed key in the current plan - there is no "apply everything" mode,
precisely because a `suspicious` row should never be rekeyed without a person having looked at
it. The rewrite happens in one transaction. ``store_product_alias`` and ``non_food_name`` both
have a (store_chain, printed name) uniqueness constraint, so moving a row can collide with one
already filed under the new key, or with a sibling row from a different old key merging into the
same new key in this same run; the surviving row keeps the higher occurrence/seen count and, for
aliases, the verified flag if either side had it.

    python -m scripts.rekey_store_chains                        # dry run (the default)
    python -m scripts.rekey_store_chains --apply lidi-suomi-ky   # rewrites just this key
    python -m scripts.rekey_store_chains --dry-run               # same as no flag, spelled out

Production is read-only to the agents that build this; the operator runs ``--apply``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.models.non_food_name import NonFoodName
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.services.store_chain import ChainMatch, match_chain, normalize_store_chain

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _default_sessions() -> AbstractAsyncContextManager[AsyncSession]:
    return app_session.AsyncSessionLocal()


def _recompute(old_key: str) -> ChainMatch | None:
    """What `match_chain` finds for an already-stored key, re-read as a header - if anything.

    A stored key is itself the output of an earlier call: either one of the known chain keys,
    or a slug of the original header (spaces and punctuation collapsed to hyphens). The fuzzy
    (and hyphen-rejoin) passes work on whitespace-separated header words, so a misread chain's
    word only surfaces again if the hyphens standing in for the original spaces are put back
    first. This also round-trips an already-correct key like ``k-group`` back to itself (``k
    group`` rejoins to the literal pattern ``K-GROUP`` by the same hyphen-rejoin rule that
    recovers a genuine misread), so it needs no special-casing against a key that was never a
    slug to begin with.
    """
    return match_chain(old_key.replace("-", " "))


@dataclass
class ChainKeyRow:
    old_key: str
    new_key: str
    rule: str | None  # "exact", "fuzzy", or None (stayed a slug / unrecognised)
    token: str | None  # the header word, or hyphen-joined pair, that matched - if any
    receipt_count: int
    alias_count: int
    non_food_count: int

    @property
    def changed(self) -> bool:
        return self.old_key != self.new_key

    @property
    def suspicious(self) -> bool:
        """An exact-rule match on an already-stored key is unexpected.

        A key that needed no tolerance at all to match a pattern is not the OCR-misread case
        this script is for; it is at least as likely to be an ordinary word that happens to
        contain one (``kirpputori-sale``, a flea market, next to the `SALE` pattern). Flagged
        so the operator reviews it instead of it being auto-applied the same as a `fuzzy` fix.
        """
        return self.changed and self.rule == "exact"


async def _counts(db: AsyncSession, model: type, column) -> dict[str, int]:
    rows = (
        await db.execute(
            select(column, func.count()).where(column.isnot(None)).group_by(column)
        )
    ).all()
    return dict(rows)


async def plan(db: AsyncSession) -> list[ChainKeyRow]:
    """Every distinct chain key in play, what it would become, and how much it covers."""
    receipts = await _counts(db, Receipt, Receipt.store_chain)
    aliases = await _counts(db, StoreProductAlias, StoreProductAlias.store_chain)
    non_food = await _counts(db, NonFoodName, NonFoodName.store_chain)
    keys = set(receipts) | set(aliases) | set(non_food)
    rows = []
    for key in sorted(keys):
        match = _recompute(key)
        new_key = (
            match.key if match is not None else (normalize_store_chain(key) or key)
        )
        rows.append(
            ChainKeyRow(
                old_key=key,
                new_key=new_key,
                rule=match.rule if match is not None else None,
                token=match.token if match is not None else None,
                receipt_count=receipts.get(key, 0),
                alias_count=aliases.get(key, 0),
                non_food_count=non_food.get(key, 0),
            )
        )
    return rows


async def _merge_unique(
    db: AsyncSession,
    model: type,
    name_attr: str,
    old_key: str,
    new_key: str,
    *,
    weight_attr: str,
    verified_attr: str | None,
) -> int:
    """Move every `model` row filed under `old_key` to `new_key`. Returns rows touched.

    `model` has a unique constraint on (store_chain, <name_attr>). A move that would collide
    keeps the row with the higher `weight_attr`, ORs `verified_attr` (if there is one) into the
    survivor, and deletes the other row.
    """
    chain_col = model.store_chain
    rows = (await db.execute(select(model).where(chain_col == old_key))).scalars().all()
    touched = 0
    for row in rows:
        name = getattr(row, name_attr)
        existing = (
            await db.execute(
                select(model).where(
                    chain_col == new_key, getattr(model, name_attr) == name
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            row.store_chain = new_key
            touched += 1
            continue
        if getattr(row, weight_attr) > getattr(existing, weight_attr):
            keep, drop = row, existing
        else:
            keep, drop = existing, row
        if verified_attr is not None:
            setattr(
                keep,
                verified_attr,
                bool(getattr(row, verified_attr) or getattr(existing, verified_attr)),
            )
        # The dropped row still holds (new_key, name) until its DELETE is flushed; moving
        # the survivor onto that same pair in the same flush can race it and trip the
        # unique constraint, so the delete goes first, in its own flush.
        await db.delete(drop)
        await db.flush()
        keep.store_chain = new_key
        await db.flush()
        touched += 1
    return touched


async def apply(db: AsyncSession, rows: list[ChainKeyRow], keys: Sequence[str]) -> int:
    """Rewrite exactly the named keys, in one transaction. Returns rows touched.

    Refuses (raises `ValueError`, nothing written) if a name is not a changed key in `rows` -
    there is no "apply everything" mode. The operator names each key after reading the plan,
    especially a `suspicious` one, rather than this script deciding on its own which rekeys are
    safe.
    """
    by_key = {row.old_key: row for row in rows}
    wanted = []
    unknown = []
    for name in keys:
        row = by_key.get(name)
        if row is None or not row.changed:
            unknown.append(name)
        else:
            wanted.append(row)
    if unknown:
        raise ValueError(
            "not a key the current plan would re-key: " + ", ".join(unknown)
        )
    touched = 0
    for row in wanted:
        result = await db.execute(
            update(Receipt)
            .where(Receipt.store_chain == row.old_key)
            .values(store_chain=row.new_key)
        )
        touched += result.rowcount or 0
        touched += await _merge_unique(
            db,
            StoreProductAlias,
            "receipt_name",
            row.old_key,
            row.new_key,
            weight_attr="occurrence_count",
            verified_attr="manually_verified",
        )
        touched += await _merge_unique(
            db,
            NonFoodName,
            "receipt_name",
            row.old_key,
            row.new_key,
            weight_attr="times_seen",
            verified_attr=None,
        )
    await db.commit()
    return touched


def _print_plan(rows: list[ChainKeyRow]) -> None:
    changed = [row for row in rows if row.changed]
    if not changed:
        print("No chain keys need re-keying.")
        return
    for row in changed:
        flag = (
            "  [SUSPICIOUS: exact match on a stored key - review before applying]"
            if row.suspicious
            else ""
        )
        print(
            f"  {row.old_key} -> {row.new_key}  "
            f"(rule={row.rule or '?'} token={row.token!r} "
            f"receipt={row.receipt_count} alias={row.alias_count} "
            f"non_food={row.non_food_count}){flag}"
        )


async def run(
    keys: Sequence[str] | None, sessions: SessionFactory = _default_sessions
) -> int:
    async with sessions() as db:
        rows = await plan(db)
        _print_plan(rows)
        if keys:
            touched = await apply(db, rows, keys)
            print(f"applied: {touched} row(s) rewritten across {len(keys)} key(s)")
        else:
            print(
                "dry run: nothing written "
                "(pass --apply <key> [<key> ...] to rewrite those keys)"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--apply",
        nargs="+",
        metavar="KEY",
        help="rewrite exactly these old chain keys (each must be a changed key in the plan)",
    )
    group.add_argument(
        "--dry-run", action="store_true", help="list what would change (default)"
    )
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(args.apply))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
