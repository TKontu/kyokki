"""ComfyUI client (Q18-G1): the hold protocol, against a fake ComfyUI (httpx.MockTransport).

No test in this file reaches the network: every request goes through an in-process
MockTransport double, ``FakeComfyUI`` below.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import comfyui


class FakeClock:
    """A monotonic clock and an ``async sleep`` that advances it, for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


DEFAULT_OUTPUTS = [{"filename": "icon.png", "subfolder": "", "type": "output"}]


class FakeComfyUI:
    """A minimal ComfyUI double for /prompt, /history, /view, /interrupt and the hold ack.

    Anything else raises inside the handler, which is how every test here also proves the
    client never calls a disallowed endpoint.
    """

    def __init__(
        self,
        *,
        prompt_responses: list[httpx.Response] | None = None,
        history_responses: list[httpx.Response] | None = None,
        outputs: list[dict[str, str]] | None = None,
        view_status: int = 200,
        view_content: bytes = b"PNGBYTES",
        never_complete: bool = False,
        ack_status: int = 200,
        interrupt_status: int = 200,
    ) -> None:
        self.prompt_responses = list(prompt_responses or [])
        self.history_responses = list(history_responses or [])
        self.outputs = DEFAULT_OUTPUTS if outputs is None else outputs
        self.view_status = view_status
        self.view_content = view_content
        self.never_complete = never_complete
        self.ack_status = ack_status
        self.interrupt_status = interrupt_status
        self.calls: list[tuple[str, str]] = []
        self.headers_seen: list[httpx.Headers] = []
        self.ack_calls = 0
        self.interrupt_calls = 0
        self.view_calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        self.headers_seen.append(request.headers)

        if path == "/prompt":
            if self.prompt_responses:
                return self.prompt_responses.pop(0)
            return httpx.Response(200, json={"prompt_id": "p1"})
        if path.startswith("/history/"):
            if self.history_responses:
                return self.history_responses.pop(0)
            completed = not self.never_complete
            return httpx.Response(
                200,
                json={
                    "p1": {
                        "status": {"completed": completed},
                        "outputs": {"8": {"images": self.outputs}} if completed else {},
                    }
                },
            )
        if path == "/view":
            self.view_calls += 1
            return httpx.Response(self.view_status, content=self.view_content)
        if path == "/comfyui-hold/ack":
            self.ack_calls += 1
            return httpx.Response(self.ack_status, json={})
        if path == "/interrupt":
            self.interrupt_calls += 1
            return httpx.Response(self.interrupt_status, json={})
        raise AssertionError(f"disallowed endpoint reached: {request.method} {path}")

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler), base_url="http://fake-comfyui"
        )


@pytest.fixture(autouse=True)
def _comfyui_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "http://fake-comfyui")
    monkeypatch.setattr(settings, "COMFYUI_TIMEOUT", 300.0)
    monkeypatch.setattr(settings, "COMFYUI_POLL_INTERVAL", 2.0)
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-gateway-key")
    comfyui._locks.clear()
    comfyui._last_ack.clear()
    yield
    comfyui._locks.clear()
    comfyui._last_ack.clear()


WORKFLOW = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}


class TestProtocol:
    async def test_prompt_carries_the_hold_ack_header(self) -> None:
        fake = FakeComfyUI()
        client = fake.client()
        try:
            result = await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert result == [b"PNGBYTES"]
        prompt_headers = [
            h
            for (m, p), h in zip(fake.calls, fake.headers_seen, strict=True)
            if p == "/prompt"
        ]
        assert prompt_headers[0]["x-hold-ack"] == "1"

    async def test_every_request_carries_the_gateway_bearer_token(self) -> None:
        fake = FakeComfyUI()
        client = fake.client()
        try:
            await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert fake.calls  # sanity: something was called
        for headers in fake.headers_seen:
            assert headers["authorization"] == "Bearer test-gateway-key"

    async def test_polls_history_until_completed(self) -> None:
        pending = httpx.Response(
            200, json={"p1": {"status": {"completed": False}, "outputs": {}}}
        )
        fake = FakeComfyUI(history_responses=[pending, pending])
        clock = FakeClock()
        client = fake.client()
        try:
            result = await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
        finally:
            await client.aclose()

        assert result == [b"PNGBYTES"]
        history_calls = [p for m, p in fake.calls if p.startswith("/history/")]
        assert len(history_calls) == 3  # two pending, then the default completed one
        assert clock.sleeps == [2.0, 2.0]  # COMFYUI_POLL_INTERVAL between polls

    async def test_ack_is_sent_after_a_successful_fetch(self) -> None:
        fake = FakeComfyUI()
        client = fake.client()
        try:
            await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert fake.ack_calls == 1
        # The ack must come after the /view fetch, never before.
        view_index = fake.calls.index(("GET", "/view"))
        ack_index = fake.calls.index(("POST", "/comfyui-hold/ack"))
        assert view_index < ack_index

    async def test_ack_is_sent_even_when_fetching_the_output_fails(self) -> None:
        fake = FakeComfyUI(view_status=500)
        client = fake.client()
        try:
            with pytest.raises(httpx.HTTPStatusError):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert fake.ack_calls == 1

    async def test_no_overlap_between_two_concurrent_render_calls(self) -> None:
        active = 0
        max_active = 0
        ack_order: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, max_active
            path = request.url.path
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)  # yield, giving a concurrent job a chance to overlap
            try:
                if path == "/prompt":
                    job = request.headers.get("x-job", "job")
                    return httpx.Response(200, json={"prompt_id": job})
                if path.startswith("/history/"):
                    prompt_id = path.rsplit("/", 1)[-1]
                    return httpx.Response(
                        200,
                        json={
                            prompt_id: {
                                "status": {"completed": True},
                                "outputs": {"8": {"images": DEFAULT_OUTPUTS}},
                            }
                        },
                    )
                if path == "/view":
                    return httpx.Response(200, content=b"BYTES")
                if path == "/comfyui-hold/ack":
                    ack_order.append("ack")
                    return httpx.Response(200, json={})
                raise AssertionError(f"unexpected path {path}")
            finally:
                active -= 1

        transport = httpx.MockTransport(handler)

        def make_client(job: str) -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                transport=transport, base_url="http://fake-comfyui"
            )
            client.headers["X-Job"] = job
            return client

        client_a = make_client("job-a")
        client_b = make_client("job-b")
        try:
            await asyncio.gather(
                comfyui.render(WORKFLOW, http_client=client_a),
                comfyui.render(WORKFLOW, http_client=client_b),
            )
        finally:
            await client_a.aclose()
            await client_b.aclose()

        assert max_active == 1
        assert len(ack_order) == 2

    async def test_at_least_one_second_between_the_ack_and_the_next_submit(
        self,
    ) -> None:
        fake = FakeComfyUI()
        clock = FakeClock()
        client = fake.client()
        try:
            await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
            await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
        finally:
            await client.aclose()

        # No time passed between the two calls, so the second must wait the full spacing.
        assert clock.sleeps == [1.0]

    async def test_no_extra_wait_once_enough_time_has_passed(self) -> None:
        fake = FakeComfyUI()
        clock = FakeClock()
        client = fake.client()
        try:
            await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
            clock.now += 5.0  # plenty of time passes between jobs
            await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
        finally:
            await client.aclose()

        assert clock.sleeps == []

    async def test_503_without_retry_after_fails_at_once_with_no_retry(self) -> None:
        fake = FakeComfyUI(
            prompt_responses=[httpx.Response(503, json={"error": "busy"})]
        )
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIUnavailable):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert [p for m, p in fake.calls if p == "/prompt"] == ["/prompt"]
        assert fake.ack_calls == 0

    async def test_503_with_retry_after_waits_then_succeeds(self) -> None:
        fake = FakeComfyUI(
            prompt_responses=[
                httpx.Response(503, headers={"Retry-After": "5"}, json={}),
                httpx.Response(200, json={"prompt_id": "p1"}),
            ]
        )
        clock = FakeClock()
        client = fake.client()
        try:
            result = await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
        finally:
            await client.aclose()

        assert result == [b"PNGBYTES"]
        assert [p for m, p in fake.calls if p == "/prompt"] == ["/prompt", "/prompt"]
        assert clock.sleeps[0] == 5.0

    async def test_timeout_interrupts_then_fails(self) -> None:
        fake = FakeComfyUI(never_complete=True)
        clock = FakeClock()
        client = fake.client()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(settings, "COMFYUI_TIMEOUT", 5.0)
        monkeypatch.setattr(settings, "COMFYUI_POLL_INTERVAL", 2.0)
        try:
            with pytest.raises(comfyui.ComfyUITimeout):
                await comfyui.render(
                    WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
                )
        finally:
            monkeypatch.undo()
            await client.aclose()

        assert fake.interrupt_calls == 1
        assert fake.ack_calls == 1

    async def test_401_becomes_a_comfyui_error_naming_the_key(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "unauthorized"})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://fake-comfyui"
        )
        try:
            with pytest.raises(comfyui.ComfyUIError, match="LLM_API_KEY"):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

    async def test_disabled_when_base_url_is_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        with pytest.raises(comfyui.ComfyUIDisabled):
            await comfyui.render(WORKFLOW)


class TestAckAndInterruptSurviveTheirOwnAuthFailure:
    """A 401/403 on the housekeeping calls (fix pass, review verdict #2) must never
    replace the real outcome, discard fetched images, or skip the >=1s spacing."""

    async def test_401_on_ack_after_success_still_returns_images_and_keeps_spacing(
        self,
    ) -> None:
        fake = FakeComfyUI(ack_status=401)
        clock = FakeClock()
        client = fake.client()
        try:
            result = await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
            # A second job right after: spacing must still apply despite the failed ack,
            # which only happens if _last_ack was set even though the ack got a 401.
            await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
        finally:
            await client.aclose()

        assert result == [b"PNGBYTES"]
        assert fake.ack_calls == 2
        assert clock.sleeps == [1.0]

    async def test_401_on_interrupt_after_timeout_still_raises_timeout(self) -> None:
        fake = FakeComfyUI(never_complete=True, interrupt_status=401)
        clock = FakeClock()
        client = fake.client()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(settings, "COMFYUI_TIMEOUT", 5.0)
        monkeypatch.setattr(settings, "COMFYUI_POLL_INTERVAL", 2.0)
        try:
            with pytest.raises(comfyui.ComfyUITimeout):
                await comfyui.render(
                    WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
                )
        finally:
            monkeypatch.undo()
            await client.aclose()

        assert fake.interrupt_calls == 1
        # The ack is still attempted afterwards, despite the interrupt's own 401.
        assert fake.ack_calls == 1


class TestJobFailureDetection:
    """review verdict #3: a failed or empty-output ComfyUI job must not be polled to the
    timeout, and must not be returned as a silent empty list."""

    async def test_status_str_error_raises_without_polling_to_the_timeout(self) -> None:
        error_response = httpx.Response(
            200,
            json={
                "p1": {
                    "status": {"completed": False, "status_str": "error"},
                    "outputs": {},
                }
            },
        )
        fake = FakeComfyUI(history_responses=[error_response])
        clock = FakeClock()
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIError, match="failed"):
                await comfyui.render(
                    WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
                )
        finally:
            await client.aclose()

        history_calls = [p for m, p in fake.calls if p.startswith("/history/")]
        assert len(history_calls) == 1
        assert clock.sleeps == []  # no poll-interval wait: it failed on the first check
        assert fake.ack_calls == 1  # the ack still happens through the finally

    async def test_execution_error_message_is_surfaced(self) -> None:
        error_response = httpx.Response(
            200,
            json={
                "p1": {
                    "status": {
                        "completed": False,
                        "messages": [
                            ["execution_error", {"exception_message": "LoRA missing"}]
                        ],
                    },
                    "outputs": {},
                }
            },
        )
        fake = FakeComfyUI(history_responses=[error_response])
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIError, match="LoRA missing"):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert fake.ack_calls == 1

    async def test_completed_with_no_images_raises_instead_of_returning_empty(
        self,
    ) -> None:
        fake = FakeComfyUI(outputs=[])
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIError, match="no images"):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()

        assert fake.ack_calls == 1


class TestRetryAfterParsing:
    """review verdict #5: only a finite number 0 or above is a usable Retry-After; the
    minimum wait is floored, and a persistent drain eventually gives up."""

    @pytest.mark.parametrize("retry_after", ["nan", "inf", "-inf"])
    async def test_non_finite_retry_after_fails_at_once(self, retry_after: str) -> None:
        fake = FakeComfyUI(
            prompt_responses=[
                httpx.Response(503, headers={"Retry-After": retry_after}, json={})
            ]
        )
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIUnavailable):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()
        assert [p for m, p in fake.calls if p == "/prompt"] == ["/prompt"]

    async def test_http_date_retry_after_is_unparseable_and_fails_at_once(self) -> None:
        fake = FakeComfyUI(
            prompt_responses=[
                httpx.Response(
                    503,
                    headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                    json={},
                )
            ]
        )
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIUnavailable):
                await comfyui.render(WORKFLOW, http_client=client)
        finally:
            await client.aclose()
        assert [p for m, p in fake.calls if p == "/prompt"] == ["/prompt"]

    async def test_retry_after_zero_is_floored_to_the_minimum_wait(self) -> None:
        fake = FakeComfyUI(
            prompt_responses=[
                httpx.Response(503, headers={"Retry-After": "0"}, json={}),
                httpx.Response(200, json={"prompt_id": "p1"}),
            ]
        )
        clock = FakeClock()
        client = fake.client()
        try:
            result = await comfyui.render(
                WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
            )
        finally:
            await client.aclose()
        assert result == [b"PNGBYTES"]
        assert clock.sleeps[0] == comfyui.MIN_RETRY_WAIT == 1.0

    async def test_retry_cap_gives_up_after_max_drain_retries(self) -> None:
        responses = [
            httpx.Response(503, headers={"Retry-After": "1"}, json={})
            for _ in range(comfyui.MAX_DRAIN_RETRIES + 1)
        ]
        fake = FakeComfyUI(prompt_responses=responses)
        clock = FakeClock()
        client = fake.client()
        try:
            with pytest.raises(comfyui.ComfyUIUnavailable):
                await comfyui.render(
                    WORKFLOW, http_client=client, sleep=clock.sleep, clock=clock.clock
                )
        finally:
            await client.aclose()
        prompt_calls = [p for m, p in fake.calls if p == "/prompt"]
        assert len(prompt_calls) == comfyui.MAX_DRAIN_RETRIES + 1


class TestEndpointAllowList:
    @pytest.mark.parametrize(
        "path",
        [
            "/prompt",
            "/history/abc123",
            "/view",
            "/upload/image",
            "/interrupt",
            "/comfyui-hold/ack",
            "/comfyui-hold/status",
            "/system_stats",
        ],
    )
    def test_allowed_endpoints_pass(self, path: str) -> None:
        comfyui._assert_allowed(path)  # must not raise

    @pytest.mark.parametrize(
        "path",
        [
            "/api/models/unload",
            "/api/inflight/1/cancel",
            "/queue",
            "/object_info",
        ],
    )
    def test_disallowed_endpoints_are_refused(self, path: str) -> None:
        with pytest.raises(comfyui.ComfyUIError):
            comfyui._assert_allowed(path)


class TestUploadImageAndHoldStatus:
    async def test_upload_image_posts_to_upload_image(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["headers"] = request.headers
            return httpx.Response(200, json={"name": "ref.png"})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://fake-comfyui"
        )
        try:
            result = await comfyui.upload_image("ref.png", b"data", http_client=client)
        finally:
            await client.aclose()

        assert seen["path"] == "/upload/image"
        assert seen["headers"]["authorization"] == "Bearer test-gateway-key"
        assert result == {"name": "ref.png"}

    async def test_upload_image_disabled_when_base_url_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        with pytest.raises(comfyui.ComfyUIDisabled):
            await comfyui.upload_image("ref.png", b"data")

    async def test_hold_status_gets_comfyui_hold_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/comfyui-hold/status"
            return httpx.Response(200, json={"open": False})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://fake-comfyui"
        )
        try:
            result = await comfyui.hold_status(http_client=client)
        finally:
            await client.aclose()

        assert result == {"open": False}

    async def test_hold_status_disabled_when_base_url_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        with pytest.raises(comfyui.ComfyUIDisabled):
            await comfyui.hold_status()
