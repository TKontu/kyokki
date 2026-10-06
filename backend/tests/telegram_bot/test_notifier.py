"""The notifier edits the acknowledgement once the worker has read the receipt (MVP-R3)."""

import logging
from uuid import uuid4

import pytest

from app.models.receipt import Receipt
from app.models.telegram_receipt_message import TelegramReceiptMessage
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
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

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
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

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
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

    assert await notifier.check_once() == 0

    assert telegram.edited == []
    assert (receipt.id, 1001) in notifier.pending


async def test_deleted_receipt_is_reported_and_forgotten(db_session, session_factory):
    receipt = await _receipt(db_session, ReceiptStatus.QUEUED)
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory)
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)
    await db_session.delete(receipt)
    await db_session.commit()

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
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

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


# CL5: the watch list lives in the database, other sources reach Telegram, and the
# message links to the review page.


async def _row(db, receipt_id, chat_id) -> TelegramReceiptMessage | None:
    return await db.get(
        TelegramReceiptMessage, (receipt_id, chat_id), populate_existing=True
    )


async def test_a_watched_receipt_is_edited_by_a_restarted_notifier_exactly_once(
    db_session, session_factory
):
    receipt = await _receipt(db_session, ReceiptStatus.QUEUED)
    before_restart = ResultNotifier(FakeTelegram(), session_factory)
    await before_restart.watch(receipt.id, chat_id=1001, message_id=55)

    # The worker reads it while the bot is down
    receipt.processing_status = ReceiptStatus.COMPLETED
    receipt.ocr_structured = {"method": "text", "lines": LINES}
    await db_session.commit()

    telegram = FakeTelegram()
    after_restart = ResultNotifier(telegram, session_factory)
    assert await after_restart.check_once() == 1

    ((chat_id, message_id, text),) = telegram.edited
    assert (chat_id, message_id) == (1001, 55)
    assert text.startswith("S-group, date not read: 1 item, 0 matched.")
    row = await _row(db_session, receipt.id, 1001)
    assert row is not None and row.notified_at is not None

    # Neither this instance nor yet another restart edits it again
    assert await after_restart.check_once() == 0
    assert await ResultNotifier(telegram, session_factory).check_once() == 0
    assert len(telegram.edited) == 1
    assert telegram.sent == []


async def test_watch_writes_an_unnotified_row(db_session, session_factory):
    receipt = await _receipt(db_session, ReceiptStatus.QUEUED)
    notifier = ResultNotifier(FakeTelegram(), session_factory)

    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

    row = await _row(db_session, receipt.id, 1001)
    assert row is not None
    assert row.message_id == 55
    assert row.notified_at is None


async def test_a_mail_or_folder_receipt_read_after_start_goes_to_every_allowed_chat_once(
    db_session, session_factory
):
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, chat_ids=[1001, 2002])
    receipt = await _receipt(
        db_session,
        ReceiptStatus.COMPLETED,
        ocr_structured={"method": "text", "lines": LINES},
        items_extracted=1,
    )

    assert await notifier.check_once() == 2
    assert await notifier.check_once() == 0
    restarted = ResultNotifier(telegram, session_factory, chat_ids=[1001, 2002])
    assert await restarted.check_once() == 0

    assert telegram.edited == []
    assert sorted(chat for chat, _ in telegram.sent) == [1001, 2002]
    for _, text in telegram.sent:
        assert text.startswith("S-group, date not read: 1 item, 0 matched.")
    for chat_id in (1001, 2002):
        row = await _row(db_session, receipt.id, chat_id)
        assert row is not None and row.notified_at is not None


async def test_a_failed_mail_receipt_is_reported_too(db_session, session_factory):
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, chat_ids=[1001])
    await _receipt(db_session, ReceiptStatus.FAILED, error="Receipt processing failed")

    assert await notifier.check_once() == 1
    assert telegram.sent[0][1].startswith("Couldn't read the receipt")


async def test_a_receipt_still_being_read_is_not_announced_yet(
    db_session, session_factory
):
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, chat_ids=[1001])
    receipt = await _receipt(db_session, ReceiptStatus.PROCESSING)

    assert await notifier.check_once() == 0
    assert telegram.sent == []

    receipt.processing_status = ReceiptStatus.COMPLETED
    await db_session.commit()
    assert await notifier.check_once() == 1


async def test_receipts_created_before_the_bot_started_are_not_replayed(
    db_session, session_factory
):
    await _receipt(db_session, ReceiptStatus.COMPLETED)
    await _receipt(db_session, ReceiptStatus.FAILED)
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, chat_ids=[1001])

    assert await notifier.check_once() == 0
    assert telegram.sent == []


async def test_a_receipt_uploaded_through_the_bot_is_not_sent_twice(
    db_session, session_factory
):
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, chat_ids=[1001, 2002])
    receipt = await _receipt(db_session, ReceiptStatus.QUEUED)
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

    receipt.processing_status = ReceiptStatus.COMPLETED
    await db_session.commit()

    assert await notifier.check_once() == 1
    assert await notifier.check_once() == 0
    assert [(chat, message) for chat, message, _ in telegram.edited] == [(1001, 55)]
    assert telegram.sent == []
    assert await _row(db_session, receipt.id, 2002) is None


async def test_a_failed_send_to_one_chat_does_not_block_the_others(
    db_session, session_factory
):
    class OneChatDown(FakeTelegram):
        async def send_message(self, chat_id, text):
            if chat_id == 2002:
                raise TelegramError("Telegram sendMessage failed: chat not found")
            return await super().send_message(chat_id, text)

    telegram = OneChatDown()
    notifier = ResultNotifier(telegram, session_factory, chat_ids=[1001, 2002])
    receipt = await _receipt(db_session, ReceiptStatus.COMPLETED)

    assert await notifier.check_once() == 1
    assert [chat for chat, _ in telegram.sent] == [1001]
    # The other chat stays pending and is retried on a later poll
    row = await _row(db_session, receipt.id, 2002)
    assert row is not None and row.notified_at is None


@pytest.mark.parametrize(
    "public_url", ["https://kyokki.example", "https://kyokki.example/"]
)
async def test_the_result_links_to_the_review_page_when_a_public_url_is_set(
    db_session, session_factory, public_url
):
    receipt = await _receipt(db_session, ReceiptStatus.COMPLETED)
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, public_url=public_url)
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

    await notifier.check_once()

    text = telegram.edited[0][2]
    assert text.endswith(f"\nhttps://kyokki.example/receipt/{receipt.id}")
    assert "example//receipt" not in text


async def test_without_a_public_url_there_is_no_link(db_session, session_factory):
    receipt = await _receipt(db_session, ReceiptStatus.COMPLETED)
    telegram = FakeTelegram()
    notifier = ResultNotifier(telegram, session_factory, public_url="")
    await notifier.watch(receipt.id, chat_id=1001, message_id=55)

    await notifier.check_once()

    text = telegram.edited[0][2]
    assert "/receipt/" not in text
    assert text.endswith("Review on the iPad.")
