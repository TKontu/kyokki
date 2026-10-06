"""The `telegram_receipt_message` table: which chats were told about which receipt (CL5)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.crud import telegram_receipt_message as crud
from app.models.receipt import Receipt
from app.models.telegram_receipt_message import TelegramReceiptMessage
from app.schemas.receipt import ReceiptStatus


async def _receipt(db, status: str = ReceiptStatus.QUEUED, **fields) -> Receipt:
    receipt = Receipt(
        id=uuid4(),
        image_path=f"data/receipts/{uuid4()}.pdf",
        processing_status=status,
        items_extracted=0,
        items_matched=0,
        **fields,
    )
    db.add(receipt)
    await db.commit()
    return receipt


async def test_watch_then_mark_notified(db_session):
    receipt = await _receipt(db_session)

    await crud.watch(db_session, receipt.id, chat_id=1001, message_id=55)
    await db_session.commit()
    pending = await crud.unnotified(db_session)
    assert [(r.receipt_id, r.chat_id, r.message_id) for r in pending] == [
        (receipt.id, 1001, 55)
    ]

    await crud.mark_notified(db_session, receipt.id, 1001)
    await db_session.commit()
    assert await crud.unnotified(db_session) == []


async def test_watching_twice_keeps_one_row_with_the_latest_message(db_session):
    receipt = await _receipt(db_session)

    await crud.watch(db_session, receipt.id, chat_id=1001, message_id=55)
    await crud.watch(db_session, receipt.id, chat_id=1001, message_id=56)
    await db_session.commit()

    rows = (await db_session.scalars(select(TelegramReceiptMessage))).all()
    assert [(r.chat_id, r.message_id) for r in rows] == [(1001, 56)]


async def test_rows_go_with_their_receipt(db_session):
    receipt = await _receipt(db_session)
    await crud.watch(db_session, receipt.id, chat_id=1001, message_id=55)
    await db_session.commit()

    await db_session.delete(receipt)
    await db_session.commit()
    db_session.expunge_all()

    assert (await db_session.scalars(select(TelegramReceiptMessage))).all() == []


async def test_unannounced_finds_finished_receipts_without_a_row(db_session):
    start = datetime.now(UTC) - timedelta(minutes=1)
    old = await _receipt(
        db_session, ReceiptStatus.COMPLETED, created_at=start - timedelta(hours=1)
    )
    done = await _receipt(db_session, ReceiptStatus.COMPLETED)
    failed = await _receipt(db_session, ReceiptStatus.FAILED)
    confirmed = await _receipt(db_session, ReceiptStatus.CONFIRMED)
    await _receipt(db_session, ReceiptStatus.QUEUED)
    await _receipt(db_session, ReceiptStatus.PROCESSING)
    watched = await _receipt(db_session, ReceiptStatus.COMPLETED)
    await crud.watch(db_session, watched.id, chat_id=1001, message_id=55)
    await db_session.commit()

    found = await crud.unannounced_finished_receipt_ids(db_session, since=start)

    assert set(found) == {done.id, failed.id, confirmed.id}
    assert old.id not in found


async def test_unannounced_is_bounded(db_session):
    start = datetime.now(UTC) - timedelta(minutes=1)
    for _ in range(3):
        await _receipt(db_session, ReceiptStatus.COMPLETED)

    found = await crud.unannounced_finished_receipt_ids(
        db_session, since=start, limit=2
    )

    assert len(found) == 2


async def test_claim_for_chats_adds_one_unsent_row_per_chat(db_session):
    receipt = await _receipt(db_session, ReceiptStatus.COMPLETED)

    await crud.claim_for_chats(db_session, receipt.id, [1001, 2002])
    await crud.claim_for_chats(db_session, receipt.id, [1001, 2002])
    await db_session.commit()

    pending = await crud.unnotified(db_session)
    assert sorted((r.chat_id, r.message_id) for r in pending) == [
        (1001, None),
        (2002, None),
    ]
