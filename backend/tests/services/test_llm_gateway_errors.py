"""GW-1: a gateway 401 names LLM_API_KEY, and a draining 503 is waited out, at every
existing LLM call site.

Each site is driven through its real ``httpx.AsyncClient`` (monkeypatched to a
``MockTransport``) - this exercises the real request path, not a fully mocked client.

Q18-G2 note: icons used to be one of these sites (the model drew an SVG); generation now
goes through ComfyUI, not the LLM gateway, so it is out of this matrix. ComfyUI's own
auth/drain/timeout handling has its own tests in ``test_comfyui.py``.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.services import (
    catalog_estimates,
    llm_extractor,
    product_selection,
)
from app.services.llm_extractor import CategoryOption, LLMExtractionError
from app.services.receipt_processing import ReceiptProcessingService

CATEGORIES = [CategoryOption(id="dairy", name="Dairy & Eggs")]
RECEIPT_TEXT = "MAITO 1,00"


def _route(monkeypatch: pytest.MonkeyPatch, module: Any, respond) -> dict:
    """Point `module`'s real AsyncClient at a fake gateway; returns what it saw."""
    seen: dict = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["count"] += 1
        seen["last_auth"] = request.headers.get("authorization")
        return respond(request, seen["count"])

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client(*_args, **kwargs):
        return real(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(module.httpx, "AsyncClient", client)
    return seen


def _ok_extraction(_request: httpx.Request, _count: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps({"p": []})}}]},
    )


def _ok_selection(_request: httpx.Request, _count: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps({"r": []})}}]},
    )


def _ok_estimate(_request: httpx.Request, _count: int) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})


async def _run_extraction() -> None:
    await llm_extractor.extract_from_text(RECEIPT_TEXT, CATEGORIES)


async def _run_selection() -> None:
    line = product_selection.SelectionLine(
        line_id="a",
        printed="MAITO",
        generic="Milk",
        category="dairy",
        candidate_ids=("00000000-0000-0000-0000-000000000001",),
        candidate_names=("Milk",),
    )
    await product_selection.select_products([line])


async def _run_estimate() -> None:
    await catalog_estimates._complete(
        [catalog_estimates.EstimateRequest(id="1", name="Milk", category="dairy")]
    )


SITES = [
    pytest.param(
        llm_extractor,
        _run_extraction,
        _ok_extraction,
        LLMExtractionError,
        id="extraction",
    ),
    pytest.param(
        product_selection,
        _run_selection,
        _ok_selection,
        LLMExtractionError,
        id="selection",
    ),
    pytest.param(
        catalog_estimates,
        _run_estimate,
        _ok_estimate,
        LLMExtractionError,
        id="estimate",
    ),
]


class TestAuthErrorsAtEveryCallSite:
    @pytest.mark.parametrize("module, run, ok_response, error_cls", SITES)
    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_401_or_403_is_the_llm_api_key_message(
        self, monkeypatch, module, run, ok_response, error_cls, status
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "top-secret-token")
        _route(monkeypatch, module, lambda request, count: httpx.Response(status))

        with pytest.raises(error_cls) as caught:
            await run()

        message = str(caught.value)
        assert "LLM_API_KEY" in message
        assert "top-secret-token" not in message

    @pytest.mark.parametrize("module, run, ok_response, error_cls", SITES)
    async def test_the_key_never_reaches_the_log_records(
        self, monkeypatch, caplog, module, run, ok_response, error_cls
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "top-secret-token")
        _route(monkeypatch, module, lambda request, count: httpx.Response(401))
        caplog.set_level("DEBUG")

        with pytest.raises(error_cls):
            await run()

        for record in caplog.records:
            assert "top-secret-token" not in str(record.__dict__)


class TestDrainAtEveryCallSite:
    @pytest.mark.parametrize("module, run, ok_response, error_cls", SITES)
    async def test_a_drain_that_clears_before_the_timeout_still_succeeds(
        self, monkeypatch, module, run, ok_response, error_cls
    ) -> None:
        def respond(request: httpx.Request, count: int) -> httpx.Response:
            if count == 1:
                # The call sites use the real, non-injectable sleep, so this waits out
                # llm_http.MIN_RETRY_WAIT for real (a real gateway would not send less
                # than that either); the drain-backoff *logic* itself (honouring
                # Retry-After within the timeout budget, the minimum wait, the retry
                # cap) is unit-tested with an injected clock in test_llm_http.py.
                return httpx.Response(503, headers={"Retry-After": "0"})
            return ok_response(request, count)

        seen = _route(monkeypatch, module, respond)

        await run()  # must not raise

        assert seen["count"] == 2

    @pytest.mark.parametrize("module, run, ok_response, error_cls", SITES)
    async def test_a_503_without_retry_after_is_not_retried(
        self, monkeypatch, module, run, ok_response, error_cls
    ) -> None:
        seen = _route(monkeypatch, module, lambda request, count: httpx.Response(503))

        with pytest.raises(error_cls):
            await run()

        assert seen["count"] == 1


class TestTimeoutIsNeverRetried:
    @pytest.mark.parametrize("module, run, ok_response, error_cls", SITES)
    async def test_a_timeout_makes_exactly_one_request(
        self, monkeypatch, module, run, ok_response, error_cls
    ) -> None:
        post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))

        class _Client:
            def __init__(self, *_args, **_kwargs) -> None:
                self.post = post

            async def __aenter__(self) -> "_Client":
                return self

            async def __aexit__(self, *_exc: object) -> None:
                return None

        monkeypatch.setattr(module.httpx, "AsyncClient", _Client)

        with pytest.raises(error_cls):
            await run()

        assert post.await_count == 1


class TestAuthErrorReachesTheStoredReceiptError:
    """Fix pass finding 4: the operator reads ``receipt.error``, not a lower-level message.

    Drives a mocked gateway 401 through the real extraction call chain and
    ``ReceiptProcessingService.process_receipt`` end to end, on the text path with no
    heuristic fallback (no product lines to recover), which is the route where the raw
    LLM failure reaches the receipt's stored error unfiltered.
    """

    # No product lines the heuristic parser could recover (same idea as
    # test_receipt_processing.py's UNREADABLE_TEXT): the auth failure is not masked by a
    # successful fallback.
    UNREADABLE_TEXT = "S-MARKET\n~~ blurred ~~\nYHTEENSÄ 7,48"

    async def test_a_401_on_the_text_path_with_no_fallback_reaches_receipt_error(
        self, monkeypatch, db_session
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "top-secret-token")
        _route(monkeypatch, llm_extractor, lambda request, count: httpx.Response(401))

        receipt = Receipt(
            id=uuid4(),
            image_path="/tmp/does-not-need-to-exist.png",
            processing_status="uploaded",
            items_extracted=0,
            items_matched=0,
        )
        db_session.add(receipt)
        await db_session.commit()

        with patch(
            "app.services.receipt_processing.extract_text_from_receipt",
            new_callable=AsyncMock,
            return_value=self.UNREADABLE_TEXT,
        ):
            service = ReceiptProcessingService(db_session)
            result = await service.process_receipt(receipt)

        assert result.success is False
        assert result.error is not None
        assert "LLM_API_KEY" in result.error
        assert "top-secret-token" not in result.error

        await db_session.refresh(receipt)
        assert receipt.processing_status == ReceiptStatus.FAILED
        assert receipt.error is not None
        assert "LLM_API_KEY" in receipt.error
        assert "top-secret-token" not in receipt.error
