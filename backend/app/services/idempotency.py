"""`Idempotency-Key`: a retried agent request replays its first response (AG2).

The flow a route follows:

1. ``claim_for(key, route, payload)`` - None when the caller sent no key, and then nothing
   is stored at all.
2. ``replay(db, claim)`` - the stored status and body when the same key and the same body
   arrived within 24 hours; ``IdempotencyConflict`` when the key came back with a different
   body. It also takes a transaction-scoped advisory lock on (route, key), so a retry that
   races the original waits for it instead of running beside it - as long as the original
   commits only once, together with ``remember``.
3. Do the work, then ``remember(db, claim, status, body)`` before the commit that makes the
   work permanent, so the response and the change land together.

Work that commits on its own before ``remember`` (quick add) would drop that
transaction-scoped lock at its first commit. It runs steps 2 and 3 inside ``held(db,
claim)`` instead, which holds a session-level lock on (route, key) on a connection of its
own until the response is stored, so the racing retry still waits and then replays.

Only successes are remembered: a refused request changed nothing, and retrying it re-asks.
"""

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.logging import get_logger
from app.models.idempotency_key import IdempotencyKey

logger = get_logger(__name__)

#: How long a key is remembered. After this the same key is a new request.
KEY_LIFETIME = timedelta(hours=24)


class IdempotencyConflict(Exception):
    """The key was used before for a different request."""


@dataclass(frozen=True)
class IdempotencyClaim:
    key: str
    route: str
    request_hash: str


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: Any


def _lock_id(claim: IdempotencyClaim, space: int) -> Any:
    """The advisory lock id of (route, key). ``replay``'s transaction lock takes space 0,
    ``held``'s session lock space 1, so holding one never waits on the other."""
    return func.hashtextextended(f"{claim.route}\n{claim.key}", space)


def request_hash(payload: Any) -> str:
    """sha256 hex of the canonical JSON form: sorted keys, no insignificant whitespace."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def claim_for(key: str | None, route: str, payload: Any) -> IdempotencyClaim | None:
    """What a request with this key claims, or None when it sent no key."""
    if not key:
        return None
    return IdempotencyClaim(key=key, route=route, request_hash=request_hash(payload))


async def replay(db: AsyncSession, claim: IdempotencyClaim) -> StoredResponse | None:
    """The response to replay for this claim, or None when the request is new.

    Raises:
        IdempotencyConflict: The key was used on this route for a different body in the
            last 24 hours.
    """
    await db.execute(select(func.pg_advisory_xact_lock(_lock_id(claim, 0))))
    row: Any = (
        (
            await db.execute(
                select(IdempotencyKey)
                .where(IdempotencyKey.key == claim.key)
                .where(IdempotencyKey.route == claim.route)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )
    if row is None or row.created_at < datetime.now(UTC) - KEY_LIFETIME:
        return None
    if row.request_hash != claim.request_hash:
        raise IdempotencyConflict(
            f"Idempotency-Key {claim.key!r} was already used for a different request"
        )
    logger.info(
        "Idempotent replay", extra={"route": claim.route, "status": row.status_code}
    )
    return StoredResponse(status_code=int(row.status_code), body=row.response)


@asynccontextmanager
async def held(db: AsyncSession, claim: IdempotencyClaim | None) -> AsyncIterator[None]:
    """Hold (route, key) across commits, until the block ends: a retry with the same key
    waits here, then finds the stored response.

    For work that commits before its response is remembered. The lock is session-level,
    so it lives on a connection of its own: the session hands its connection back to the
    pool at every commit. No claim, no lock.
    """
    if claim is None:
        yield
        return
    bind = db.bind
    engine = bind if isinstance(bind, AsyncEngine) else bind.engine
    async with engine.connect() as lock:
        await lock.execute(select(func.pg_advisory_lock(_lock_id(claim, 1))))
        await lock.commit()
        try:
            yield
        finally:
            try:
                await lock.execute(select(func.pg_advisory_unlock(_lock_id(claim, 1))))
                await lock.commit()
            except BaseException:
                # A pooled connection would keep the lock: close it instead.
                await lock.invalidate()
                raise


async def remember(
    db: AsyncSession, claim: IdempotencyClaim, status_code: int, body: Any
) -> None:
    """Stage the response for this claim in the caller's transaction; does not commit.

    Overwrites an expired row for the same key and route.
    """
    values = {
        "key": claim.key,
        "route": claim.route,
        "request_hash": claim.request_hash,
        "status_code": status_code,
        "response": body,
        "created_at": datetime.now(UTC),
    }
    statement = insert(IdempotencyKey).values(**values)
    await db.execute(
        statement.on_conflict_do_update(
            constraint="uq_idempotency_key_key_route",
            set_={name: statement.excluded[name] for name in values},
        )
    )
