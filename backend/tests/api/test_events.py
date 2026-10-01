"""Tests for the SSE live-updates endpoint (A5).

``GET /api/events`` is the browser-reachable twin of ``/api/ws``: the iPad PWA cannot
hold a bearer token (AG1), so this is how a broadcast reaches it instead of a direct
WebSocket. See ``app/api/endpoints/events.py`` and ``app/services/websockets.py``.

These tests drive ``_event_stream`` (the async generator behind the endpoint) directly
rather than through an HTTP client. httpx's ``ASGITransport`` (and Starlette's
``TestClient``, which is built on it) runs the whole ASGI application to completion
before handing back a response — fine for ordinary request/response endpoints, but it
means it cannot observe a response that is still streaming, which is exactly what this
endpoint is for the life of a connection. The end-to-end proof against a real socket is
the manual streaming check in the PR description instead.
"""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.endpoints.events as events_module
from app.api.endpoints.events import _event_stream, events_stream
from app.core.api_tokens import hash_secret
from app.core.config import settings
from app.services.websockets import SSE_QUEUE_MAXSIZE, ConnectionManager, manager


@pytest.fixture(autouse=True)
def _clear_sse_subscribers():
    """Isolate tests: the endpoint uses the process-wide singleton ``manager``."""
    manager._sse_subscribers.clear()
    yield
    manager._sse_subscribers.clear()


class _FakeRequest:
    """A minimal stand-in for ``fastapi.Request``, controllable from a test."""

    def __init__(self) -> None:
        self.force_disconnected = False

    async def is_disconnected(self) -> bool:
        return self.force_disconnected


async def _drain_to_stop(gen) -> None:
    """Assert the generator ends (cleans up) once told the client is gone."""
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=2)


class TestEventStreamResponse:
    """The endpoint wires a StreamingResponse with the right shape, cheaply.

    This never iterates the body — only subscribing (the first iteration) does that.
    """

    async def test_response_headers(self) -> None:
        response = await events_stream(_FakeRequest())
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        assert len(manager._sse_subscribers) == 0


class TestEventStreamDelivery:
    """A broadcast reaches the generator as one ``data:`` line."""

    async def test_message_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(events_module, "DISCONNECT_POLL_SECONDS", 0.02)
        request = _FakeRequest()
        gen = _event_stream(request)
        message = {
            "type": "inventory_update",
            "timestamp": "2026-10-01T00:00:00+00:00",
            "entity_id": "11111111-1111-1111-1111-111111111111",
            "data": {"action": "created"},
        }

        async def publish() -> None:
            await asyncio.sleep(0.05)
            await manager.broadcast(json.dumps(message))

        publisher = asyncio.create_task(publish())
        try:
            line = await asyncio.wait_for(gen.__anext__(), timeout=2)
        finally:
            await publisher

        assert line == f"data: {json.dumps(message)}\n\n"
        assert len(manager._sse_subscribers) == 1

        request.force_disconnected = True
        await _drain_to_stop(gen)
        assert len(manager._sse_subscribers) == 0

    async def test_multiple_streams_each_get_the_broadcast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(events_module, "DISCONNECT_POLL_SECONDS", 0.02)
        request_a, request_b = _FakeRequest(), _FakeRequest()
        gen_a, gen_b = _event_stream(request_a), _event_stream(request_b)
        message = {
            "type": "receipt_status",
            "timestamp": "2026-10-01T00:00:00+00:00",
            "entity_id": "22222222-2222-2222-2222-222222222222",
            "data": {"status": "completed"},
        }

        # Start both consumers (each subscribes on its first iteration) before
        # publishing, or whichever one starts later misses the broadcast.
        task_a = asyncio.create_task(gen_a.__anext__())
        task_b = asyncio.create_task(gen_b.__anext__())
        for _ in range(50):
            if len(manager._sse_subscribers) == 2:
                break
            await asyncio.sleep(0.01)
        assert len(manager._sse_subscribers) == 2

        await manager.broadcast(json.dumps(message))
        line_a = await asyncio.wait_for(task_a, timeout=2)
        line_b = await asyncio.wait_for(task_b, timeout=2)

        expected = f"data: {json.dumps(message)}\n\n"
        assert line_a == expected
        assert line_b == expected
        assert len(manager._sse_subscribers) == 2

        request_a.force_disconnected = True
        request_b.force_disconnected = True
        await _drain_to_stop(gen_a)
        await _drain_to_stop(gen_b)
        assert len(manager._sse_subscribers) == 0

    async def test_heartbeat_while_idle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(events_module, "DISCONNECT_POLL_SECONDS", 0.02)
        monkeypatch.setattr(events_module, "HEARTBEAT_INTERVAL_SECONDS", 0.05)
        request = _FakeRequest()
        gen = _event_stream(request)

        line = await asyncio.wait_for(gen.__anext__(), timeout=2)
        assert line == ": heartbeat\n\n"

        request.force_disconnected = True
        await _drain_to_stop(gen)


class TestEventStreamCleanup:
    """No leaked subscription after a client disconnects."""

    async def test_cleanup_on_disconnect_before_any_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(events_module, "DISCONNECT_POLL_SECONDS", 0.02)
        request = _FakeRequest()
        gen = _event_stream(request)

        # Start the generator (subscribes), without it ever receiving a message.
        task = asyncio.create_task(gen.__anext__())
        for _ in range(50):
            if len(manager._sse_subscribers) == 1:
                break
            await asyncio.sleep(0.01)
        assert len(manager._sse_subscribers) == 1

        request.force_disconnected = True
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(task, timeout=2)
        assert len(manager._sse_subscribers) == 0

    async def test_unsubscribe_is_idempotent(self) -> None:
        test_manager = ConnectionManager()
        queue = test_manager.subscribe_sse()
        test_manager.unsubscribe_sse(queue)
        assert queue not in test_manager._sse_subscribers
        test_manager.unsubscribe_sse(queue)  # a second disconnect must not raise


class TestSSEQueueOverflow:
    """A slow client is bounded, not blocked and not unbounded (A5)."""

    def test_overflow_drops_oldest_and_sends_resync(self) -> None:
        test_manager = ConnectionManager()
        queue = test_manager.subscribe_sse()

        for i in range(SSE_QUEUE_MAXSIZE + 5):
            test_manager._publish_sse(json.dumps({"type": "probe", "seq": i}))

        # Bounded: never grew past the cap even though more than that many
        # messages were published and nothing ever drained it.
        assert queue.qsize() <= SSE_QUEUE_MAXSIZE

        items = []
        while not queue.empty():
            items.append(json.loads(queue.get_nowait()))

        assert len(items) == SSE_QUEUE_MAXSIZE
        resync_items = [item for item in items if item["type"] == "resync"]
        probe_seqs = {item["seq"] for item in items if item["type"] == "probe"}

        assert resync_items, "an overflow should leave at least one resync event"
        # The oldest probes were dropped to make room...
        assert 0 not in probe_seqs
        # ...and the very message that caused the last overflow was replaced by
        # a resync rather than enqueued itself.
        assert (SSE_QUEUE_MAXSIZE + 4) not in probe_seqs
        # A probe from the initial, non-overflowing fill survives untouched.
        assert (SSE_QUEUE_MAXSIZE - 1) in probe_seqs

    def test_a_manager_with_no_subscribers_does_not_error(self) -> None:
        test_manager = ConnectionManager()
        test_manager._publish_sse(json.dumps({"type": "probe"}))  # no-op, no raise


class TestEventsAuth:
    """AG1: /api/events needs a read-scoped token like any other GET.

    Only the rejection path is exercised over HTTP: the success path never
    completes a response (see the module docstring), so it is covered instead
    by the generic, route-agnostic GET coverage in ``test_auth.py`` plus
    ``TestEventStreamResponse`` above proving the endpoint itself is wired
    normally into the ``/api`` router (which is where the token dependency
    lives).
    """

    SECRET = "events-test-secret-value"

    @pytest.fixture(autouse=True)
    def _tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            settings, "KYOKKI_API_TOKENS", [f"ipad:read:{hash_secret(self.SECRET)}"]
        )

    async def test_rejected_without_a_token(self) -> None:
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/api/events")
        assert response.status_code == 401
