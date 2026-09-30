"""The shared gateway POST helper (GW-1): auth errors, drain backoff, no retry on timeout."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.config import settings
from app.services.llm_http import LLMAuthError, post_chat

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

    async def test_the_key_never_reaches_the_log_records(
        self, monkeypatch, caplog
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "sekret-token")
        transport = httpx.MockTransport(lambda request: httpx.Response(401))
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


class TestTimeout:
    async def test_a_timeout_propagates_with_exactly_one_request(self) -> None:
        client = MagicMock()
        client.post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(httpx.ReadTimeout):
            await post_chat(client, PAYLOAD, budget=10.0)

        assert client.post.await_count == 1
