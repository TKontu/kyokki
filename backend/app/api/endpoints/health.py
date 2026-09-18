"""Liveness and readiness.

Two different questions, deliberately on two routes (H03):

- ``/api/health/live`` — is the process up? Nothing else. This is what the
  container healthcheck and the frontend's ``depends_on`` gate use, so a slow or
  blipping PostgreSQL can never restart-loop the API.
- ``/api/health`` — can it actually serve? Checks PostgreSQL and Redis inside a
  one-second budget and answers 503 when either is unreachable. This is the one
  the runbook tells the operator to read; before H03 it returned ``{"status":
  "ok"}`` from a function with no dependencies and could not fail while the
  process was alive, which made "both return healthy" meaningless.
"""

import asyncio

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db

router = APIRouter()
logger = get_logger(__name__)

# The whole readiness check, not per dependency: an operator refreshing the page
# on a bad day should still get an answer rather than a hanging request.
READINESS_TIMEOUT_SECONDS = 1.0


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """The process is running. Used by the container healthcheck."""
    return {"status": "ok"}


async def _check_postgres(db: AsyncSession) -> None:
    await db.execute(text("SELECT 1"))


async def _check_redis() -> None:
    from app.services.broadcast_helpers import get_redis_client

    client = await get_redis_client()
    await client.ping()


@router.get("/health")
async def readiness(
    response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """PostgreSQL and Redis, within one second. 503 when either is unreachable."""
    checks = {"postgres": _check_postgres(db), "redis": _check_redis()}

    async def run(name: str, check) -> tuple[str, str]:
        try:
            await asyncio.wait_for(check, timeout=READINESS_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - any failure is "not ready"
            logger.warning(
                "Readiness check failed",
                extra={"dependency": name, "error": repr(exc)},
            )
            return name, "unavailable"
        return name, "ok"

    results = dict(
        await asyncio.gather(*(run(name, check) for name, check in checks.items()))
    )

    ready = all(state == "ok" for state in results.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ok" if ready else "degraded", **results}
