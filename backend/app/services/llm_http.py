"""One shared POST to the LLM gateway's chat completions endpoint (GW-1).

The gateway turned on API-key authentication on 2026-09-30 and the four call sites
(``llm_extractor``, ``product_selection``, ``catalog_estimates``, ``product_icons``) each
sent the request inline. This module is the one place that:

- sends the bearer header built from ``settings.LLM_API_KEY``;
- turns a 401/403 into a clear, distinct :class:`LLMAuthError` that names ``LLM_API_KEY``
  and never carries the key or any header;
- waits out a ``503`` that carries ``Retry-After`` (the gateway draining for a redeploy),
  as long as the wait still fits inside the caller's overall ``timeout``, then retries
  once more; a ``503`` without ``Retry-After``, and every other status, is returned
  exactly as httpx gave it, for the caller's own ``raise_for_status()`` to raise;
- never retries a timeout - that is an ``httpx.TimeoutException`` the caller already
  catches, and it propagates from here unchanged.

The sleep and the clock are injectable so tests never wait for real.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SleepFn = Callable[[float], Awaitable[None]]
ClockFn = Callable[[], float]


class LLMAuthError(httpx.HTTPStatusError):
    """The gateway rejected ``LLM_API_KEY`` (401/403).

    The message names the setting to fix, never the key's value or any header.
    """


def _parse_retry_after(value: str) -> float | None:
    """Seconds, or an HTTP date (RFC 9110 10.2.3); ``None`` if neither parses."""
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


async def post_chat(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    *,
    budget: float,
    sleep: SleepFn = asyncio.sleep,
    clock: ClockFn = time.monotonic,
) -> httpx.Response:
    """POST ``payload`` to ``{settings.LLM_BASE_URL}/chat/completions`` with the bearer
    header, waiting out a drain within ``budget``.

    ``budget`` is the caller's overall time allowance (the same value it gives
    ``httpx.AsyncClient(timeout=...)``) - not an `asyncio` cancellation timeout, so it is
    named to keep clear of ASYNC109 rather than to dodge it.

    Raises:
        LLMAuthError: the gateway answered 401 or 403.
        httpx.HTTPError: any other transport or timeout failure, exactly as httpx raises
            it. The caller keeps its own ``response.raise_for_status()`` for status
            errors, including a 503 this function gave up retrying.
    """
    url = f"{settings.LLM_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    started = clock()

    while True:
        response = await client.post(url, json=payload, headers=headers)

        if response.status_code in (401, 403):
            raise LLMAuthError(
                f"the LLM gateway rejected LLM_API_KEY (HTTP {response.status_code})",
                request=response.request,
                response=response,
            )

        if response.status_code == 503:
            retry_after = response.headers.get("Retry-After")
            wait = _parse_retry_after(retry_after) if retry_after is not None else None
            if wait is not None and (clock() - started) + wait < budget:
                logger.info(
                    f"gateway draining, retrying in {wait:g} s",
                    extra={"retry_after_seconds": wait},
                )
                await sleep(wait)
                continue

        return response
