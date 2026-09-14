"""The receipt worker claims queued receipts and reads them one at a time (MVP-R3)."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.schemas.receipt import ReceiptStatus
from app.services.llm_extractor import LLMExtractionError
from app.worker import receipt_worker

OCR = "app.services.receipt_processing.extract_text_from_receipt"
TEXT = "app.services.receipt_processing.extract_from_text"


@pytest.fixture(autouse=True)
def quiet_broadcasts():
    with (
        patch(
            "app.services.receipt_queue.broadcast_receipt_status",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.receipt_processing.broadcast_receipt_status",
            new_callable=AsyncMock,
        ),
        patch(
            "app.worker.receipt_worker.broadcast_receipt_status", new_callable=AsyncMock
        ),
    ):
        yield


async def _queued(
    db: AsyncSession, tmp_path, minutes_ago: int = 1, **fields
) -> Receipt:
    path = tmp_path / f"{uuid4()}.pdf"
    path.write_bytes(b"%PDF fake")
    receipt = Receipt(
        id=uuid4(),
        image_path=str(path),
        processing_status=ReceiptStatus.QUEUED,
        queued_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        items_extracted=0,
        items_matched=0,
        **fields,
    )
    db.add(receipt)
    await db.commit()
    return receipt


def _extraction(*names: str) -> ReceiptExtraction:
    return ReceiptExtraction(
        method="text",
        store_chain="S-MARKET",
        lines=[ExtractedLine(name=name, quantity=1) for name in names],
    )


async def test_claims_and_processes_the_receipt(db_session, session_factory, tmp_path):
    receipt = await _queued(db_session, tmp_path, error="old failure")

    with (
        patch(OCR, new_callable=AsyncMock, return_value="S-MARKET text"),
        patch(TEXT, new_callable=AsyncMock, return_value=_extraction("MAITO")),
    ):
        worked = await receipt_worker.run_once(session_factory)

    assert worked is True
    await db_session.refresh(receipt)
    assert receipt.processing_status == ReceiptStatus.COMPLETED
    assert receipt.items_extracted == 1
    assert receipt.error is None
    assert receipt.processing_started_at is not None


async def test_extraction_failure_is_stored(db_session, session_factory, tmp_path):
    receipt = await _queued(db_session, tmp_path)

    with (
        patch(OCR, new_callable=AsyncMock, return_value="text"),
        patch(
            TEXT, new_callable=AsyncMock, side_effect=LLMExtractionError("timed out")
        ),
    ):
        await receipt_worker.run_once(session_factory)

    await db_session.refresh(receipt)
    assert receipt.processing_status == ReceiptStatus.FAILED
    assert "timed out" in receipt.error


async def test_crash_outside_the_pipeline_still_fails_the_receipt(
    db_session, session_factory, tmp_path
):
    receipt = await _queued(db_session, tmp_path)

    with patch(
        "app.worker.receipt_worker.ReceiptProcessingService.process_receipt",
        side_effect=RuntimeError("boom"),
    ):
        worked = await receipt_worker.run_once(session_factory)

    assert worked is True
    await db_session.refresh(receipt)
    assert receipt.processing_status == ReceiptStatus.FAILED
    assert "boom" in receipt.error


async def test_empty_queue_does_nothing(db_session, session_factory):
    with patch(
        "app.worker.receipt_worker.ReceiptProcessingService.process_receipt"
    ) as process:
        assert await receipt_worker.run_once(session_factory) is False
    process.assert_not_called()


async def test_receipts_are_read_oldest_first(db_session, session_factory, tmp_path):
    newer = await _queued(db_session, tmp_path, minutes_ago=1)
    older = await _queued(db_session, tmp_path, minutes_ago=5)
    order: list = []

    async def record(self, receipt):
        order.append(receipt.id)

    with patch(
        "app.worker.receipt_worker.ReceiptProcessingService.process_receipt", record
    ):
        await receipt_worker.run_once(session_factory)
        await receipt_worker.run_once(session_factory)

    assert order == [older.id, newer.id]


async def test_stale_processing_receipt_is_failed(
    db_session, session_factory, tmp_path
):
    stuck = await _queued(db_session, tmp_path)
    stuck.processing_status = ReceiptStatus.PROCESSING
    stuck.processing_started_at = datetime.now(UTC) - timedelta(minutes=30)
    await db_session.commit()

    assert await receipt_worker.run_once(session_factory) is False

    await db_session.refresh(stuck)
    assert stuck.processing_status == ReceiptStatus.FAILED
    assert "did not finish" in stuck.error


async def test_run_sleeps_only_when_the_queue_is_empty(session_factory):
    results = iter([True, True, False, True])
    sleeps: list[float] = []

    async def fake_run_once(factory):
        try:
            return next(results)
        except StopIteration:
            raise asyncio.CancelledError from None

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    with (
        patch.object(receipt_worker, "run_once", fake_run_once),
        pytest.raises(asyncio.CancelledError),
    ):
        await receipt_worker.run(session_factory, poll_seconds=2.0, sleep=fake_sleep)

    assert sleeps == [2.0]


async def test_run_survives_an_unexpected_error(session_factory):
    calls = 0
    sleeps: list[float] = []

    async def flaky(factory):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("database restarting")
        raise asyncio.CancelledError

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    with (
        patch.object(receipt_worker, "run_once", flaky),
        pytest.raises(asyncio.CancelledError),
    ):
        await receipt_worker.run(session_factory, poll_seconds=2.0, sleep=fake_sleep)

    assert calls == 2
    assert sleeps == [2.0]
