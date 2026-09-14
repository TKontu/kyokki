"""Bot process: long-poll Telegram and report results of receipts read by the worker."""

import asyncio
import logging
from typing import Any, Protocol

from app.core.config import Settings
from app.core.logging import get_logger, setup_logging
from app.core.service_runner import run_service
from app.telegram_bot.client import TelegramClient
from app.telegram_bot.handlers import BotHandler
from app.telegram_bot.notifier import ResultNotifier

logger = get_logger(__name__)

MAX_BACKOFF_SECONDS = 60.0


class _Updates(Protocol):
    async def get_updates(
        self, offset: int | None, poll_seconds: int
    ) -> list[dict[str, Any]]: ...


class _Handler(Protocol):
    async def handle_update(self, update: dict[str, Any]) -> None: ...


def quiet_http_loggers() -> None:
    """httpx logs every request URL at INFO, and Bot API URLs contain the token."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def poll_loop(
    client: _Updates,
    handler: _Handler,
    poll_seconds: int,
    backoff_base: float = 1.0,
) -> None:
    offset: int | None = None
    failures = 0
    while True:
        try:
            updates = await client.get_updates(offset=offset, poll_seconds=poll_seconds)
        except Exception as exc:
            failures += 1
            delay = min(backoff_base * 2 ** (failures - 1), MAX_BACKOFF_SECONDS)
            logger.warning(
                "Telegram polling failed, retrying",
                extra={"error": str(exc), "retry_in_seconds": delay},
            )
            await asyncio.sleep(delay)
            continue
        failures = 0
        for update in updates:
            # Advance past every update, even one the handler fails on, so it is not redelivered forever
            offset = int(update["update_id"]) + 1
            try:
                await handler.handle_update(update)
            except Exception:
                logger.exception(
                    "Telegram update failed", extra={"update_id": update["update_id"]}
                )


def configure_logging() -> None:
    setup_logging()
    # After setup: the root handlers would otherwise print httpx request URLs with the token
    quiet_http_loggers()


async def run(settings: Settings) -> None:
    quiet_http_loggers()
    if settings.TELEGRAM_BOT_TOKEN is None:
        # Idle instead of exiting, so a compose service with restart: unless-stopped does not loop
        logger.info("Telegram bot disabled (TELEGRAM_BOT_TOKEN not set)")
        await asyncio.Event().wait()
        return

    from app.db.session import AsyncSessionLocal

    if not settings.TELEGRAM_ALLOWED_CHAT_IDS:
        logger.warning(
            "TELEGRAM_ALLOWED_CHAT_IDS is empty: the bot only answers /start with the chat id"
        )

    client = TelegramClient(
        token=settings.TELEGRAM_BOT_TOKEN.get_secret_value(),
        base_url=settings.TELEGRAM_API_BASE,
    )
    notifier = ResultNotifier(client, AsyncSessionLocal)
    handler = BotHandler(
        client=client,
        session_factory=AsyncSessionLocal,
        notifier=notifier,
        allowed_chat_ids=settings.TELEGRAM_ALLOWED_CHAT_IDS,
    )
    logger.info(
        "Telegram bot started",
        extra={"allowed_chats": len(settings.TELEGRAM_ALLOWED_CHAT_IDS)},
    )
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(
                poll_loop(client, handler, poll_seconds=settings.TELEGRAM_POLL_TIMEOUT)
            )
            tasks.create_task(notifier.run())
    finally:
        await client.aclose()


def main() -> None:
    from app.core.config import settings

    configure_logging()
    run_service(lambda: run(settings), "Telegram bot")
