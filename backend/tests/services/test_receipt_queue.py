"""Postgres-backed receipt queue: enqueue, FIFO claim, stale recovery (MVP-R3)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.services import receipt_queue

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def broadcasts():
    with patch(
        "app.services.receipt_queue.broadcast_receipt_status", new_callable=AsyncMock
    ) as broadcast:
        yield broadcast


async def _receipt(db: AsyncSession, status: str, **fields) -> Receipt:
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


class TestEnqueue:
    async def test_marks_queued_and_resets_previous_failure(
        self, db_session, broadcasts
    ):
        receipt = await _receipt(
            db_session,
            ReceiptStatus.FAILED,
            error="LLM timed out",
            processing_started_at=NOW - timedelta(minutes=30),
        )

        await receipt_queue.enqueue(db_session, receipt, now=NOW)

        await db_session.refresh(receipt)
        assert receipt.processing_status == ReceiptStatus.QUEUED
        assert receipt.queued_at == NOW
        assert receipt.error is None
        assert receipt.processing_started_at is None
        broadcasts.assert_awaited_once()
        assert broadcasts.await_args.kwargs["status"] == "queued"


class TestClaim:
    async def test_takes_the_oldest_queued_receipt(self, db_session, broadcasts):
        newer = await _receipt(db_session, ReceiptStatus.QUEUED, queued_at=NOW)
        older = await _receipt(
            db_session, ReceiptStatus.QUEUED, queued_at=NOW - timedelta(minutes=5)
        )
        await _receipt(
            db_session, ReceiptStatus.FAILED, queued_at=NOW - timedelta(hours=1)
        )

        claimed = await receipt_queue.claim_next(db_session, now=NOW)

        assert claimed is not None
        assert claimed.id == older.id
        assert claimed.processing_status == ReceiptStatus.PROCESSING
        assert claimed.processing_started_at == NOW
        assert broadcasts.await_args.kwargs["status"] == "processing"
        second = await receipt_queue.claim_next(db_session, now=NOW)
        assert second is not None and second.id == newer.id

    async def test_empty_queue_returns_none(self, db_session, broadcasts):
        await _receipt(db_session, ReceiptStatus.COMPLETED, queued_at=NOW)

        assert await receipt_queue.claim_next(db_session, now=NOW) is None
        broadcasts.assert_not_awaited()

    async def test_retried_receipt_goes_behind_newer_ones(self, db_session):
        failed = await _receipt(
            db_session, ReceiptStatus.FAILED, queued_at=NOW - timedelta(hours=1)
        )
        waiting = await _receipt(
            db_session, ReceiptStatus.QUEUED, queued_at=NOW - timedelta(minutes=1)
        )

        await receipt_queue.enqueue(db_session, failed, now=NOW)

        first = await receipt_queue.claim_next(db_session, now=NOW)
        assert first is not None and first.id == waiting.id

    async def test_a_locked_receipt_is_skipped_by_another_claimer(
        self, db_engine, committed_db_session
    ):
        # Two more connections have to see these rows, so they are committed for
        # real rather than living in the transaction db_session rolls back.
        locked = await _receipt(
            committed_db_session,
            ReceiptStatus.QUEUED,
            queued_at=NOW - timedelta(minutes=2),
        )
        free = await _receipt(
            committed_db_session,
            ReceiptStatus.QUEUED,
            queued_at=NOW - timedelta(minutes=1),
        )
        factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as holder, factory() as claimer:
            # The first worker has claimed `locked` but not committed yet
            await holder.execute(
                select(Receipt).where(Receipt.id == locked.id).with_for_update()
            )
            claimed = await receipt_queue.claim_next(claimer, now=NOW)
            await holder.rollback()

        assert claimed is not None
        assert claimed.id == free.id


class TestStale:
    async def test_only_old_processing_receipts_fail(self, db_session, broadcasts):
        stale = await _receipt(
            db_session,
            ReceiptStatus.PROCESSING,
            processing_started_at=NOW - timedelta(minutes=11),
        )
        fresh = await _receipt(
            db_session,
            ReceiptStatus.PROCESSING,
            processing_started_at=NOW - timedelta(minutes=9),
        )
        done = await _receipt(
            db_session,
            ReceiptStatus.COMPLETED,
            processing_started_at=NOW - timedelta(hours=2),
        )

        assert await receipt_queue.fail_stale(db_session, now=NOW) == 1

        for receipt in (stale, fresh, done):
            await db_session.refresh(receipt)
        assert stale.processing_status == ReceiptStatus.FAILED
        assert "did not finish within 10 minutes" in stale.error
        assert fresh.processing_status == ReceiptStatus.PROCESSING
        assert done.processing_status == ReceiptStatus.COMPLETED
        broadcasts.assert_awaited_once()
        assert broadcasts.await_args.kwargs["status"] == "failed"

    async def test_nothing_stale_does_nothing(self, db_session, broadcasts):
        assert await receipt_queue.fail_stale(db_session, now=NOW) == 0
        broadcasts.assert_not_awaited()


class TestQueuePosition:
    async def test_counts_earlier_waiting_or_running_receipts(self, db_session):
        await _receipt(
            db_session,
            ReceiptStatus.PROCESSING,
            queued_at=NOW - timedelta(minutes=3),
            processing_started_at=NOW,
        )
        await _receipt(
            db_session, ReceiptStatus.QUEUED, queued_at=NOW - timedelta(minutes=2)
        )
        await _receipt(
            db_session, ReceiptStatus.COMPLETED, queued_at=NOW - timedelta(minutes=4)
        )
        mine = await _receipt(
            db_session, ReceiptStatus.QUEUED, queued_at=NOW - timedelta(minutes=1)
        )
        await _receipt(db_session, ReceiptStatus.QUEUED, queued_at=NOW)

        assert await receipt_queue.queue_position(db_session, mine) == 2
