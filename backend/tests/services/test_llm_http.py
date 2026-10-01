"""The shared gateway POST helper (GW-1): auth errors, drain backoff, no retry on timeout."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.config import settings
from app.services.llm_http import (
    MAX_DRAIN_RETRIES,
    MIN_REQUEST_TIMEOUT,
    MIN_RETRY_WAIT,
    LLMAuthError,
    _parse_retry_after,
    post_chat,
)

PAYLOAD = {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]}


def _client_answering(*responses: httpx.Response) -> MagicMock:
    """A client whose ``post`` returns each response in turn (or repeats the last)."""
    client = MagicMock()
    remaining = list(responses)

    async def post(*_args, **_kwargs):
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0]

    client.post = AsyncMock(side_effect=post)
    return client


def _clock(*, start: float = 0.0):
    """A fake clock the helper can advance by sleeping; returns (clock, sleep)."""
    now = [start]

    async def sleep(seconds: float) -> None:
        now[0] += seconds

    def clock() -> float:
        return now[0]

    return clock, sleep


class TestRequestShape:
    async def test_sends_the_bearer_header_to_the_chat_completions_url(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "sekret-token")
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"ok": True})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await post_chat(client, PAYLOAD, budget=10.0)

        assert response.status_code == 200
        assert seen["url"] == f"{settings.LLM_BASE_URL}/chat/completions"
        assert seen["auth"] == "Bearer sekret-token"


class TestAuthErrors:
    @pytest.mark.parametrize("status", [401, 403])
    async def test_401_and_403_raise_llm_auth_error_naming_the_setting(
        self, monkeypatch, status
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "sekret-token")
        transport = httpx.MockTransport(lambda request: httpx.Response(status))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(LLMAuthError) as caught:
                await post_chat(client, PAYLOAD, budget=10.0)

        message = str(caught.value)
        assert "LLM_API_KEY" in message
        assert f"HTTP {status}" in message
        assert "sekret-token" not in message

    @pytest.mark.parametrize("status", [401, 403])
    async def test_the_key_never_reaches_the_log_records(
        self, monkeypatch, caplog, status
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "sekret-token")
        transport = httpx.MockTransport(lambda request: httpx.Response(status))
        caplog.set_level("DEBUG")

        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(LLMAuthError):
                await post_chat(client, PAYLOAD, budget=10.0)

        for record in caplog.records:
            assert "sekret-token" not in str(record.__dict__)


class TestDrainBackoff:
    async def test_a_503_with_retry_after_seconds_is_waited_out_then_retried(
        self,
    ) -> None:
        ok = httpx.Response(200, json={"done": True})
        drained = httpx.Response(503, headers={"Retry-After": "2"})
        client = _client_answering(drained, ok)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 200
        assert client.post.await_count == 2
        assert clock() == 2.0

    async def test_a_retry_after_http_date_is_honoured(self) -> None:
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        # A real wall-clock date a few seconds out. The helper's own clock (for the
        # timeout budget) is still the injected fake, so only the *parsed wait* depends
        # on real time - bounded loosely below.
        target = datetime.now(UTC) + timedelta(seconds=3)
        ok = httpx.Response(200, json={"done": True})
        drained = httpx.Response(
            503, headers={"Retry-After": format_datetime(target, usegmt=True)}
        )
        client = _client_answering(drained, ok)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 200
        assert client.post.await_count == 2
        assert 0.0 < clock() <= 4.0

    async def test_a_503_without_retry_after_is_not_retried(self) -> None:
        drained = httpx.Response(503)
        client = _client_answering(drained)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 503
        assert client.post.await_count == 1

    async def test_a_drain_longer_than_the_remaining_timeout_gives_up(self) -> None:
        # Every response drains for 100s, but the overall timeout is only 5s: the
        # helper must not retry forever, and must not retry past what the budget allows.
        drained = httpx.Response(503, headers={"Retry-After": "100"})
        client = _client_answering(drained)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=5.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 503
        assert client.post.await_count == 1
        assert clock() == 0.0  # never slept: the wait alone exceeds the timeout

    async def test_other_error_statuses_are_not_retried(self) -> None:
        error = httpx.Response(500)
        client = _client_answering(error)

        response = await post_chat(client, PAYLOAD, budget=10.0)

        assert response.status_code == 500
        assert client.post.await_count == 1

    async def test_two_drains_in_a_row_then_succeed(self) -> None:
        """The docstring says "retries", not "retries once" - every consecutive drain
        gets its own wait while the budget lasts."""
        ok = httpx.Response(200, json={"done": True})
        first_drain = httpx.Response(503, headers={"Retry-After": "2"})
        second_drain = httpx.Response(503, headers={"Retry-After": "3"})
        client = _client_answering(first_drain, second_drain, ok)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=100.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 200
        assert client.post.await_count == 3
        assert clock() == 5.0


class TestRetriedRequestTimeout:
    """Fix pass finding 1: a retry must not run with the client's full timeout again."""

    async def test_the_first_request_gets_the_full_budget(self) -> None:
        client = _client_answering(httpx.Response(200, json={}))

        await post_chat(client, PAYLOAD, budget=42.0)

        assert client.post.call_args_list[0].kwargs["timeout"] == 42.0

    async def test_a_retry_is_bounded_by_the_remaining_budget_not_the_full_one(
        self,
    ) -> None:
        ok = httpx.Response(200, json={"done": True})
        drained = httpx.Response(503, headers={"Retry-After": "2"})
        client = _client_answering(drained, ok)
        clock, sleep = _clock()

        await post_chat(client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock)

        calls = client.post.call_args_list
        assert calls[0].kwargs["timeout"] == 10.0  # first attempt: the full budget
        # after a 2 s drain wait, only 8 s of the 10 s budget remain
        assert calls[1].kwargs["timeout"] == pytest.approx(8.0)

    async def test_a_retrys_timeout_never_drops_below_the_floor(self) -> None:
        # budget 2.5s, a 2s drain wait leaves 0.5s - below MIN_REQUEST_TIMEOUT (1.0s)
        ok = httpx.Response(200, json={"done": True})
        drained = httpx.Response(503, headers={"Retry-After": "2"})
        client = _client_answering(drained, ok)
        clock, sleep = _clock()

        await post_chat(client, PAYLOAD, budget=2.5, sleep=sleep, clock=clock)

        assert client.post.call_args_list[1].kwargs["timeout"] == MIN_REQUEST_TIMEOUT


class TestMinimumRetryWait:
    """Fix pass finding 2: Retry-After: 0 must not be hammered."""

    async def test_a_zero_retry_after_is_floored_to_the_minimum_wait(self) -> None:
        ok = httpx.Response(200, json={"done": True})
        drained = httpx.Response(503, headers={"Retry-After": "0"})
        client = _client_answering(drained, ok)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 200
        assert clock() == MIN_RETRY_WAIT

    async def test_a_sub_minimum_retry_after_is_also_floored(self) -> None:
        ok = httpx.Response(200, json={"done": True})
        drained = httpx.Response(503, headers={"Retry-After": "0.2"})
        client = _client_answering(drained, ok)
        clock, sleep = _clock()

        await post_chat(client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock)

        assert clock() == MIN_RETRY_WAIT


class TestDrainRetryCap:
    """Fix pass finding 2: a persistently draining gateway must still give up."""

    async def test_consecutive_drains_stop_at_the_cap_even_with_budget_to_spare(
        self,
    ) -> None:
        # Always drains, with a huge budget: only the retry cap can stop this.
        drained = httpx.Response(503, headers={"Retry-After": "0"})
        client = _client_answering(drained)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=1_000_000.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 503
        assert client.post.await_count == 1 + MAX_DRAIN_RETRIES


class TestNonFiniteRetryAfter:
    """Fix pass finding 3: float() accepts nan/inf, which must not become a wait."""

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf", "Infinity", "-Infinity"])
    def test_non_finite_values_do_not_parse(self, value: str) -> None:
        assert _parse_retry_after(value) is None

    async def test_a_non_finite_retry_after_is_not_retried(self) -> None:
        drained = httpx.Response(503, headers={"Retry-After": "nan"})
        client = _client_answering(drained)
        clock, sleep = _clock()

        response = await post_chat(
            client, PAYLOAD, budget=10.0, sleep=sleep, clock=clock
        )

        assert response.status_code == 503
        assert client.post.await_count == 1
        assert clock() == 0.0  # never slept


class TestTimeout:
    async def test_a_timeout_propagates_with_exactly_one_request(self) -> None:
        client = MagicMock()
        client.post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(httpx.ReadTimeout):
            await post_chat(client, PAYLOAD, budget=10.0)

        assert client.post.await_count == 1
