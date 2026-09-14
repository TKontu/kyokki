"""Bot process: disabled without a token, long-poll loop otherwise."""

import asyncio
import logging

import pytest

from app.core.config import Settings
from app.telegram_bot import runner
from app.telegram_bot.client import TelegramError


async def test_without_a_token_the_bot_idles_and_never_calls_telegram(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Telegram client created without a token")

    monkeypatch.setattr(runner, "TelegramClient", forbidden)
    settings = Settings(_env_file=None, TELEGRAM_BOT_TOKEN=None)

    task = asyncio.create_task(runner.run(settings))
    await asyncio.sleep(0.05)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


class ScriptedClient:
    """Returns scripted getUpdates batches, then blocks like an idle long poll."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.offsets: list[int | None] = []

    async def get_updates(self, offset, poll_seconds):
        self.offsets.append(offset)
        if not self.batches:
            await asyncio.sleep(3600)
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch


class RecordingHandler:
    def __init__(self, fail_on: int | None = None):
        self.seen: list[int] = []
        self.fail_on = fail_on

    async def handle_update(self, update):
        self.seen.append(update["update_id"])
        if update["update_id"] == self.fail_on:
            raise RuntimeError("handler bug")


async def test_poll_loop_advances_the_offset_and_survives_errors():
    client = ScriptedClient(
        [
            [{"update_id": 10}, {"update_id": 11}],
            TelegramError("Telegram getUpdates failed: HTTP 502"),
            [{"update_id": 12}],
        ]
    )
    handler = RecordingHandler(fail_on=11)

    task = asyncio.create_task(
        runner.poll_loop(client, handler, poll_seconds=1, backoff_base=0.001)
    )
    for _ in range(400):
        if len(client.offsets) >= 4:
            break
        await asyncio.sleep(0.005)
    task.cancel()

    assert handler.seen == [10, 11, 12]
    assert client.offsets == [None, 12, 12, 13]


def test_http_loggers_are_quieted_because_urls_carry_the_token():
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)

    runner.configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
