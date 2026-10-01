"""Tests for the SSE live-updates endpoint (A5).

``GET /api/events`` is the browser-reachable twin of ``/api/ws``: the iPad PWA cannot
hold a bearer token (AG1), so this is how a broadcast reaches it instead of a direct
WebSocket. See ``app/api/endpoints/events.py`` and ``app/services/websockets.py``.

Most of these tests drive ``_event_stream`` (the async generator behind the endpoint)
directly rather than through an HTTP client. httpx's ``ASGITransport`` (and Starlette's
``TestClient``, which is built on it) runs the whole ASGI application to completion
before handing back a response — fine for ordinary request/response endpoints, but it
means it cannot even report a status code for a response that is still streaming, which
is exactly what this endpoint is for the life of a connection. ``TestRealAppOverRealSocket``
below is the one exception: it proves the real route end to end (status, headers, auth)
over an actual uvicorn server, where that limitation does not apply. The manual streaming
check in the PR description is what additionally proves delivery through the Next.js proxy.
"""

import asyncio
import json
import logging

import pytest
import uvicorn
from httpx import ASGITransport, AsyncClient

import app.api.endpoints.events as events_module
from app.api.endpoints.events import HEARTBEAT_EVENT, _event_stream, events_stream
from app.core.api_tokens import hash_secret
from app.core.config import settings
from app.services.websockets import SSE_QUEUE_MAXSIZE, ConnectionManager, manager


def _overflow_logs(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "sse_client_overflow"]


def _queue_contents(queue: "asyncio.Queue[str]") -> list[dict]:
    """Peek a queue's contents without consuming them."""
    return [json.loads(item) for item in queue._queue]  # type: ignore[attr-defined]


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
        # "no-transform" is load-bearing (F1): without it, Next's standalone server
        # gzips this response and never flushes the gzip stream until it closes, so a
        # browser (which always sends Accept-Encoding: gzip) gets nothing until the
        # connection ends.
        assert response.headers["cache-control"] == "no-cache, no-transform"
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
        # A named event, not a bare SSE comment (F2): EventSource never surfaces a
        # comment to JavaScript, so a client-side staleness watchdog needs something
        # `addEventListener('ping', ...)` can actually see.
        assert line == HEARTBEAT_EVENT
        assert line.startswith("event: ping\n")

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

    def test_overflow_drops_oldest_and_sends_a_resync(self) -> None:
        test_manager = ConnectionManager()
        queue = test_manager.subscribe_sse()

        for i in range(SSE_QUEUE_MAXSIZE):
            test_manager._publish_sse(json.dumps({"type": "probe", "seq": i}))
        assert queue.qsize() == SSE_QUEUE_MAXSIZE  # full, but not yet an overflow

        test_manager._publish_sse(
            json.dumps({"type": "probe", "seq": SSE_QUEUE_MAXSIZE})
        )

        # Still bounded, not grown.
        assert queue.qsize() == SSE_QUEUE_MAXSIZE
        contents = _queue_contents(queue)
        resync_items = [item for item in contents if item["type"] == "resync"]
        probe_seqs = {item["seq"] for item in contents if item["type"] == "probe"}

        assert len(resync_items) == 1
        # The oldest probe was dropped to make room...
        assert 0 not in probe_seqs
        # ...and the message that caused the overflow was replaced by the resync
        # rather than enqueued itself.
        assert SSE_QUEUE_MAXSIZE not in probe_seqs
        # A probe from the initial, non-overflowing fill survives untouched.
        assert (SSE_QUEUE_MAXSIZE - 1) in probe_seqs

    def test_repeated_overflow_keeps_at_most_one_pending_resync(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """F3: a client that stays behind gets one resync and one log per episode,
        not one of each per message published while it is still behind."""
        caplog.set_level(logging.WARNING)
        test_manager = ConnectionManager()
        queue = test_manager.subscribe_sse()

        for i in range(SSE_QUEUE_MAXSIZE):
            test_manager._publish_sse(json.dumps({"type": "probe", "seq": i}))
        assert _overflow_logs(caplog) == []

        # First overflow of the episode: the usual drop-oldest-and-resync, one log.
        test_manager._publish_sse(json.dumps({"type": "probe", "seq": 100}))
        after_first_overflow = _queue_contents(queue)
        assert sum(1 for item in after_first_overflow if item["type"] == "resync") == 1
        assert len(_overflow_logs(caplog)) == 1

        # More messages arrive while the client is still behind: no second resync
        # stacks up, no second log, and the queue is left exactly as it was - the
        # new messages are simply dropped, since the client already has a resync
        # queued that will tell it to catch up on everything.
        for i in range(101, 106):
            test_manager._publish_sse(json.dumps({"type": "probe", "seq": i}))
        assert _queue_contents(queue) == after_first_overflow
        assert len(_overflow_logs(caplog)) == 1

        # The client fully catches up: its consumer drains the whole queue,
        # including the resync that was telling it to do exactly that.
        while not queue.empty():
            queue.get_nowait()

        # A later overflow is then a new episode: its own resync, its own log -
        # the earlier episode left nothing behind to confuse it with.
        for i in range(SSE_QUEUE_MAXSIZE):
            test_manager._publish_sse(json.dumps({"type": "probe", "seq": 200 + i}))
        test_manager._publish_sse(json.dumps({"type": "probe", "seq": 999}))
        assert len(_overflow_logs(caplog)) == 2
        contents = _queue_contents(queue)
        assert sum(1 for item in contents if item["type"] == "resync") == 1

    def test_unsubscribe_drops_the_resync_pending_flag_too(self) -> None:
        test_manager = ConnectionManager()
        queue = test_manager.subscribe_sse()
        test_manager.unsubscribe_sse(queue)
        assert queue not in test_manager._sse_resync_pending

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


class TestRealAppOverRealSocket:
    """F4: the real route, with real auth, end to end.

    ``ASGITransport`` (and ``TestClient``, built on it - see the module docstring) runs
    the whole app to completion in one call before it will hand back anything at all, so
    it cannot even report a status code for a response that is still streaming. A real
    socket does not have that problem: headers arrive as soon as the server sends them,
    independently of whether the body is finished, so this spins up the real app on an
    actual uvicorn server (a free port, no lifespan - nothing here needs the Redis
    listener) and makes a real HTTP request against it.
    """

    SECRET = "events-real-server-secret-value"

    @pytest.fixture(autouse=True)
    def _tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            settings, "KYOKKI_API_TOKENS", [f"ipad:read:{hash_secret(self.SECRET)}"]
        )

    @pytest.fixture
    async def base_url(self):
        from app.main import app as real_app

        config = uvicorn.Config(
            real_app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            lifespan="off",
        )
        server = uvicorn.Server(config)
        task = asyncio.create_task(server.serve())
        for _ in range(500):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started, "uvicorn did not start in time"
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)

    async def test_returns_200_with_the_event_stream_headers(
        self, base_url: str
    ) -> None:
        async with (
            AsyncClient(base_url=base_url) as ac,
            ac.stream(
                "GET",
                "/api/events",
                headers={"Authorization": f"Bearer {self.SECRET}"},
            ) as response,
        ):
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            # Same two header assertions as F1 above, now proven over a real
            # socket rather than by constructing the StreamingResponse directly.
            assert response.headers["cache-control"] == "no-cache, no-transform"
            assert response.headers["x-accel-buffering"] == "no"

    async def test_rejected_without_a_token_over_a_real_socket(
        self, base_url: str
    ) -> None:
        async with AsyncClient(base_url=base_url) as ac:
            response = await ac.get("/api/events")
        assert response.status_code == 401
