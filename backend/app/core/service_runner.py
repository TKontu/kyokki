"""Run a long-lived async service until SIGTERM/SIGINT (worker, Telegram bot)."""

import asyncio
import contextlib
import signal
from collections.abc import Callable, Coroutine
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


async def run_until_stopped(
    coro_factory: Callable[[], Coroutine[Any, Any, None]], name: str
) -> None:
    """Run the service; a stop signal cancels it and it exits cleanly."""
    task = asyncio.create_task(coro_factory())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        # Not supported on Windows, where Ctrl+C still raises KeyboardInterrupt
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        logger.info(f"{name} stopped")


def run_service(
    coro_factory: Callable[[], Coroutine[Any, Any, None]], name: str
) -> None:
    asyncio.run(run_until_stopped(coro_factory, name))
