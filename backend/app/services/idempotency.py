"""`Idempotency-Key`: a retried agent request replays its first response (AG2).

The flow a route follows:

1. ``claim_for(key, route, body)`` - None when the caller sent no key, and then nothing is
   stored at all.
2. ``replay(db, claim)`` - the stored status and body when the same key and the same body
   arrived within 24 hours; ``IdempotencyConflict`` when the key came back with a different
   body. It also takes a transaction-scoped advisory lock on (route, key), so a retry that
   races the original waits for it instead of running beside it.
3. Do the work, then ``remember(db, claim, status, body)`` before the commit that makes the
   work permanent, so the response and the change land together.

Only successes are remembered: a refused request changed nothing, and retrying it re-asks.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

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
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f"{claim.route}\n{claim.key}", 0)
            )
        )
    )
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
