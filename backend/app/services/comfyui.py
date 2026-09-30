"""ComfyUI client (Q18-G1): the hold protocol from docs/spikes/Q18_icon_styles.md.

The GPU host (192.168.0.94) is shared. This client is the only place Kyokki talks to it,
and it follows the operator's mandatory protocol:

1. ``POST /prompt`` with ``X-Hold-Ack: 1`` opens a hold and returns a ``prompt_id``.
2. Poll ``GET /history/{prompt_id}`` until ``status.completed``.
3. Fetch every output with ``GET /view``.
4. ``POST /comfyui-hold/ack`` only once the files are in hand (or the job has failed).
5. Sleep at least a second before the next job to the same base URL.
6. Never more than one job in flight per base URL.

Nothing here talks to ComfyUI while ``COMFYUI_BASE_URL`` is empty (:class:`ComfyUIDisabled`).
A hard allow-list keeps this client from ever reaching an endpoint the operator did not name.
Configuration (base URL, the overall budget, the poll interval, the gateway key) always comes
from ``app.core.config.settings`` - never hardcode the host.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# The only ComfyUI endpoints this client (or a caller through it) may ever reach.
ALLOWED_PATHS = frozenset(
    {
        "/prompt",
        "/history",
        "/view",
        "/upload/image",
        "/interrupt",
        "/comfyui-hold/ack",
        "/comfyui-hold/status",
        "/system_stats",
    }
)

# At least this long between the previous job's ack and the next job's submit, per base URL.
MIN_JOB_SPACING = 1.0

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class ComfyUIError(Exception):
    """Base for every error this client raises."""


class ComfyUIDisabled(ComfyUIError):
    """``COMFYUI_BASE_URL`` is empty; the client refuses to run."""

    def __init__(self) -> None:
        super().__init__("COMFYUI_BASE_URL is empty; ComfyUI is disabled")


class ComfyUIUnavailable(ComfyUIError):
    """503 from ``/prompt`` with no ``Retry-After``: the hold never opened. Do not retry."""


class ComfyUITimeout(ComfyUIError):
    """The job did not finish inside its budget. ``/interrupt`` was sent first."""


# One lock and one last-ack timestamp per base URL, shared by every caller in this
# process - this is what makes "one job in flight per base URL" true process-wide, not
# just per client instance.
_locks: dict[str, asyncio.Lock] = {}
_last_ack: dict[str, float] = {}


def _lock_for(base_url: str) -> asyncio.Lock:
    lock = _locks.get(base_url)
    if lock is None:
        lock = asyncio.Lock()
        _locks[base_url] = lock
    return lock


def _assert_allowed(path: str) -> None:
    # Exact match for every fixed endpoint, plus the /history/{prompt_id} template.
    trimmed = "/" + path.split("?", 1)[0].strip("/")
    if trimmed in ALLOWED_PATHS or trimmed.startswith("/history/"):
        return
    raise ComfyUIError(
        f"refusing to call a ComfyUI endpoint outside the allow-list: {path}"
    )


async def _guarded_request(
    client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    _assert_allowed(path)
    return await client.request(method, path, **kwargs)


def _check_auth(response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise ComfyUIError(
            f"ComfyUI rejected the request ({response.status_code}); check LLM_API_KEY"
        )


def _base_url() -> str:
    base_url = settings.COMFYUI_BASE_URL
    if not base_url:
        raise ComfyUIDisabled()
    return base_url.rstrip("/")


async def render(
    workflow: dict[str, Any],
    *,
    http_client: httpx.AsyncClient | None = None,
    sleep: Sleep | None = None,
    clock: Clock | None = None,
) -> list[bytes]:
    """Render one ComfyUI job through the hold protocol; returns each output's bytes.

    Base URL, the overall budget and the poll interval come from ``settings``
    (``COMFYUI_BASE_URL``, ``COMFYUI_TIMEOUT``, ``COMFYUI_POLL_INTERVAL``). ``http_client``
    lets a caller (or a test) supply its own ``httpx.AsyncClient``, e.g. one built on
    ``httpx.MockTransport``; ``sleep``/``clock`` default to real ``asyncio.sleep`` and
    ``time.monotonic`` and exist so a test can control timing without really waiting.

    Raises :class:`ComfyUIDisabled` when no base URL is configured,
    :class:`ComfyUIUnavailable` on a 503 with no ``Retry-After`` (nothing was queued; do
    not retry), and :class:`ComfyUITimeout` if the job does not finish before the budget
    runs out (an ``/interrupt`` is sent first). One job at a time runs against any given
    base URL, process-wide, with at least :data:`MIN_JOB_SPACING` seconds after the
    previous job's ack.
    """
    sleep = asyncio.sleep if sleep is None else sleep
    clock = time.monotonic if clock is None else clock

    base_url = _base_url()
    budget = settings.COMFYUI_TIMEOUT
    poll_interval = settings.COMFYUI_POLL_INTERVAL

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(base_url=base_url, timeout=budget)

    async with _lock_for(base_url):
        last_ack = _last_ack.get(base_url)
        if last_ack is not None:
            wait = MIN_JOB_SPACING - (clock() - last_ack)
            if wait > 0:
                await sleep(wait)
        try:
            return await _render_locked(
                client, workflow, budget, poll_interval, sleep, clock, base_url
            )
        finally:
            if owns_client:
                await client.aclose()


async def _render_locked(
    client: httpx.AsyncClient,
    workflow: dict[str, Any],
    budget: float,
    poll_interval: float,
    sleep: Sleep,
    clock: Clock,
    base_url: str,
) -> list[bytes]:
    deadline = clock() + budget
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}

    prompt_id = await _submit(client, workflow, headers, deadline, sleep, clock)
    logger.info(
        "ComfyUI job submitted", extra={"prompt_id": prompt_id, "base_url": base_url}
    )
    started = clock()
    try:
        try:
            history_entry = await _poll_until_complete(
                client, prompt_id, poll_interval, deadline, sleep, clock, headers
            )
        except ComfyUITimeout:
            await _interrupt(client, headers, prompt_id)
            logger.warning(
                "ComfyUI job timed out; sent /interrupt", extra={"prompt_id": prompt_id}
            )
            raise
        images = _extract_images(history_entry)
        outputs = [await _fetch_view(client, headers, image) for image in images]
        logger.info(
            "ComfyUI job completed",
            extra={
                "prompt_id": prompt_id,
                "seconds": round(clock() - started, 1),
                "outputs": len(outputs),
                "status": "completed",
            },
        )
        return outputs
    finally:
        await _ack(client, headers, prompt_id)
        _last_ack[base_url] = clock()


async def _submit(
    client: httpx.AsyncClient,
    workflow: dict[str, Any],
    headers: dict[str, str],
    deadline: float,
    sleep: Sleep,
    clock: Clock,
) -> str:
    submit_headers = {**headers, "X-Hold-Ack": "1"}
    while True:
        response = await _guarded_request(
            client, "POST", "/prompt", json={"prompt": workflow}, headers=submit_headers
        )
        _check_auth(response)
        if response.status_code == 503:
            retry_after = response.headers.get("Retry-After")
            if retry_after is None:
                raise ComfyUIUnavailable(
                    "ComfyUI could not open the hold (503, no Retry-After); "
                    "nothing was queued"
                )
            remaining = deadline - clock()
            if remaining <= 0:
                raise ComfyUITimeout("ComfyUI kept draining past the job budget")
            await sleep(min(float(retry_after), remaining))
            continue
        response.raise_for_status()
        prompt_id: str = response.json()["prompt_id"]
        return prompt_id


async def _poll_until_complete(
    client: httpx.AsyncClient,
    prompt_id: str,
    poll_interval: float,
    deadline: float,
    sleep: Sleep,
    clock: Clock,
    headers: dict[str, str],
) -> dict[str, Any]:
    while True:
        response = await _guarded_request(
            client, "GET", f"/history/{prompt_id}", headers=headers
        )
        _check_auth(response)
        response.raise_for_status()
        body = response.json()
        entry = body.get(prompt_id)
        if entry and entry.get("status", {}).get("completed"):
            result: dict[str, Any] = entry
            return result
        if clock() >= deadline:
            raise ComfyUITimeout(f"ComfyUI job {prompt_id} did not complete in time")
        await sleep(poll_interval)


async def _interrupt(
    client: httpx.AsyncClient, headers: dict[str, str], prompt_id: str
) -> None:
    try:
        response = await _guarded_request(client, "POST", "/interrupt", headers=headers)
        _check_auth(response)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning(
            "ComfyUI /interrupt failed", extra={"prompt_id": prompt_id}, exc_info=True
        )


async def _ack(
    client: httpx.AsyncClient, headers: dict[str, str], prompt_id: str
) -> None:
    try:
        response = await _guarded_request(
            client, "POST", "/comfyui-hold/ack", json={}, headers=headers
        )
        _check_auth(response)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning(
            "ComfyUI hold ack failed", extra={"prompt_id": prompt_id}, exc_info=True
        )


def _extract_images(history_entry: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for node_output in (history_entry.get("outputs") or {}).values():
        for image in node_output.get("images") or []:
            images.append(
                {
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                }
            )
    return images


async def _fetch_view(
    client: httpx.AsyncClient, headers: dict[str, str], image: dict[str, str]
) -> bytes:
    response = await _guarded_request(
        client, "GET", "/view", params=image, headers=headers
    )
    _check_auth(response)
    response.raise_for_status()
    return response.content


async def upload_image(
    name: str,
    data: bytes,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """``POST /upload/image``, for a later reference image (IP-Adapter)."""
    base_url = _base_url()
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(base_url=base_url)
    try:
        response = await _guarded_request(
            client,
            "POST",
            "/upload/image",
            files={"image": (name, data)},
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        )
        _check_auth(response)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
    finally:
        if owns_client:
            await client.aclose()


async def hold_status(
    *, http_client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """``GET /comfyui-hold/status``: whether someone else's hold is open right now."""
    base_url = _base_url()
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(base_url=base_url)
    try:
        response = await _guarded_request(
            client,
            "GET",
            "/comfyui-hold/status",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        )
        _check_auth(response)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
    finally:
        if owns_client:
            await client.aclose()
