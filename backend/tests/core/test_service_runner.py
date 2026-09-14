"""Long-lived services stop cleanly when cancelled (worker, Telegram bot)."""

import asyncio
import logging

from app.core.service_runner import run_until_stopped


async def test_a_cancelled_service_logs_stopped_and_returns(caplog):
    async def service() -> None:
        # What a stop signal does: the service task is cancelled while it waits
        raise asyncio.CancelledError

    with caplog.at_level(logging.INFO):
        await asyncio.wait_for(run_until_stopped(service, "Receipt worker"), timeout=2)

    assert "Receipt worker stopped" in caplog.text


async def test_a_service_that_finishes_returns_normally():
    ran = []

    async def service() -> None:
        ran.append(True)

    await run_until_stopped(service, "Once")

    assert ran == [True]
