"""The notifier edits the acknowledgement once the worker has read the receipt (MVP-R3)."""

import logging
from uuid import uuid4

import pytest

from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.telegram_bot.client import TelegramError
from app.telegram_bot.notifier import ResultNotifier

from .conftest import FakeTelegram

LINES = [
    {
        "name": "KEVYTMAITOJUOMA",
        "generic_name": "Milk",
        "quantity": 1,
        "category": "dairy",
    }
]


async def _receipt(db, status: str, **fields) -> Receipt:
    receipt = Receipt(
        id=uuid4(),
        image_path=f"data/receipts/{uuid4()}.pdf",
        processing_status=status,
        store_chain="s-group",
        **{"items_extracted": 0, "items_matched": 0, **fields},
    )
    db.add(receipt)
    await db.commit()
    return receipt


async def test_completed_receipt_edits_the_message_with_the_summary(
    db_session, session_factory
):
    receipt = await _receipt(
        db_session,
        ReceiptStatus.COMPLETED,
        ocr_structured={"method": "text", "lines": LINES},
        items_extracted=1,
    )
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory)
    notifier.watch(receipt.id, chat_id=1001, message_id=55)

    assert await notifier.check_once() == 1

    ((chat_id, message_id, text),) = telegram.edited
    assert (chat_id, message_id) == (1001, 55)
    assert text.startswith("S-group, date not read: 1 item, 0 matched.")
    assert notifier.pending == {}


async def test_failed_receipt_edits_the_message_without_the_raw_error(
    db_session, session_factory, caplog
):
    raw_reason = "Receipt processing failed: ConnectionError: http://192.168.0.94:9292"
    receipt = await _receipt(db_session, ReceiptStatus.FAILED, error=raw_reason)
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory)
    notifier.watch(receipt.id, chat_id=1001, message_id=55)

    with caplog.at_level(logging.INFO):
        await notifier.check_once()

    text = telegram.edited[0][2]
    assert text.startswith("Couldn't read the receipt")
    assert "192.168" not in text
    assert "ConnectionError" not in text
    # The raw reason still reaches the log, just not the cook-facing reply.
    assert any(
        raw_reason == getattr(r, "reason", None)
        for r in caplog.records
        if r.levelno == logging.INFO
    )


@pytest.mark.parametrize("status", [ReceiptStatus.QUEUED, ReceiptStatus.PROCESSING])
async def test_unfinished_receipt_leaves_the_message_alone(
    db_session, session_factory, status
):
    receipt = await _receipt(db_session, status)
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory)
    notifier.watch(receipt.id, chat_id=1001, message_id=55)

    assert await notifier.check_once() == 0

    assert telegram.edited == []
    assert receipt.id in notifier.pending


async def test_deleted_receipt_is_reported_and_forgotten(db_session, session_factory):
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory)
    notifier.watch(uuid4(), chat_id=1001, message_id=55)

    await notifier.check_once()

    assert telegram.edited[0][2].startswith("The receipt was deleted")
    assert notifier.pending == {}


async def test_edit_failure_falls_back_to_a_new_message(db_session, session_factory):
    class NoEdit(FakeTelegram):
        async def edit_message_text(self, chat_id, message_id, text):
            raise TelegramError(
                "Telegram editMessageText failed: message to edit not found"
            )

    receipt = await _receipt(
        db_session, ReceiptStatus.FAILED, error="Receipt processing failed: bad file"
    )
    telegram = NoEdit()
    notifier = ResultNotifier(telegram, session_factory)
    notifier.watch(receipt.id, chat_id=1001, message_id=55)

    await notifier.check_once()

    assert telegram.sent[0][0] == 1001
    assert telegram.sent[0][1].startswith("Couldn't read the receipt")
    assert "bad file" not in telegram.sent[0][1]
    assert notifier.pending == {}


async def test_run_keeps_checking_until_cancelled(session_factory):
    import asyncio

    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory)
    checks = 0

    async def fake_check():
        nonlocal checks
        checks += 1
        if checks == 1:
            raise ConnectionError("database restarting")
        if checks == 3:
            raise asyncio.CancelledError
        return 0

    async def no_sleep(seconds):
        return None

    notifier.check_once = fake_check
    with pytest.raises(asyncio.CancelledError):
        await notifier.run(poll_seconds=3.0, sleep=no_sleep)
    assert checks == 3
