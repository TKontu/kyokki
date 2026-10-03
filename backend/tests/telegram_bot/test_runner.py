"""Bot process: disabled without a token, long-poll loop otherwise."""

import asyncio
import logging

import pytest

from app.core.config import Settings
from app.telegram_bot import runner
from app.telegram_bot.client import TelegramConflict, TelegramError


async def test_without_a_token_the_bot_idles_and_never_calls_telegram(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Telegram client created without a token")

    monkeypatch.setattr(runner, "TelegramClient", forbidden)
    settings = Settings(_env_file=None, TELEGRAM_BOT_TOKEN=None)

    task = asyncio.create_task(runner.run(settings))
    # Yield to the loop rather than sleeping: the task either settles into its idle
    # state or finishes, and both are decided within a few scheduler turns.
    for _ in range(10):
        if task.done():
            break
        await asyncio.sleep(0)
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
            # Block until the test cancels the task; no timer to leave behind.
            await asyncio.Event().wait()
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
    # backoff_base is 0.001, so the error retry is the only real wait; the rest is
    # scheduler turns. Yield rather than polling on a 5 ms timer.
    for _ in range(2000):
        if len(client.offsets) >= 4:
            break
        await asyncio.sleep(0)
    task.cancel()

    assert handler.seen == [10, 11, 12]
    assert client.offsets == [None, 12, 12, 13]


def test_http_loggers_are_quieted_because_urls_carry_the_token():
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)

    runner.configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


class ConflictClient:
    """Always conflicts, or conflicts a scripted number of times then blocks like an
    idle long poll (a real recovered getUpdates call would not return instantly)."""

    def __init__(self, conflicts: int | None = None):
        self.conflicts = conflicts  # None means "forever"
        self.calls = 0

    async def get_updates(self, offset, poll_seconds):
        self.calls += 1
        if self.conflicts is None or self.calls <= self.conflicts:
            raise TelegramConflict("Telegram getUpdates failed: Conflict: terminated")
        await asyncio.Event().wait()
        return []  # pragma: no cover - never reached; the Event never fires


async def test_persistent_409_exits_non_zero_after_the_grace_period(caplog):
    client = ConflictClient(conflicts=None)
    handler = RecordingHandler()

    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as caught:
        await runner.poll_loop(
            client,
            handler,
            poll_seconds=1,
            backoff_base=0.001,
            conflict_grace_seconds=0.02,
        )

    assert caught.value.code == runner.CONFLICT_EXIT_CODE
    assert client.calls > 1  # it tolerated at least one 409 before giving up
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "another instance is polling this bot token" in message
    assert "stop it or use a separate dev token" in message


async def test_a_transient_409_does_not_exit_and_polling_continues():
    client = ConflictClient(conflicts=1)
    handler = RecordingHandler()

    task = asyncio.create_task(
        runner.poll_loop(
            client,
            handler,
            poll_seconds=1,
            backoff_base=0.001,
            conflict_grace_seconds=60.0,
        )
    )
    for _ in range(2000):
        if client.calls >= 2:
            break
        await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Recovered after the single conflict, so it never hit the exit path.
    assert client.calls >= 2


async def test_non_409_errors_still_retry_without_the_conflict_exit():
    client = ScriptedClient(
        [
            TelegramError("Telegram getUpdates failed: HTTP 502"),
            TelegramError("Telegram getUpdates failed: HTTP 502"),
            [{"update_id": 1}],
        ]
    )
    handler = RecordingHandler()

    task = asyncio.create_task(
        runner.poll_loop(
            client,
            handler,
            poll_seconds=1,
            backoff_base=0.001,
            conflict_grace_seconds=0.001,
        )
    )
    for _ in range(2000):
        if len(client.offsets) >= 4:
            break
        await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert handler.seen == [1]
