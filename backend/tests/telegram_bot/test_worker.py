"""The worker reads queued receipts one at a time and edits the acknowledgement."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.services.llm_extractor import LLMExtractionError
from app.services.receipt_ingest import ingest_receipt_file
from app.telegram_bot.handlers import Job
from app.telegram_bot.worker import ReceiptWorker

from .conftest import FakeTelegram

OCR = "app.services.receipt_processing.extract_text_from_receipt"
TEXT = "app.services.receipt_processing.extract_from_text"


async def _job(db_session, content: bytes = b"%PDF order", message_id: int = 55) -> Job:
    result = await ingest_receipt_file(
        db_session, content=content, filename="o.pdf", content_type="application/pdf"
    )
    return Job(receipt_id=result.receipt.id, chat_id=1001, message_id=message_id)


async def test_job_processes_and_edits_the_message_with_the_summary(
    db_session, session_factory
):
    job = await _job(db_session)
    telegram = FakeTelegram()
    extraction = ReceiptExtraction(
        method="text",
        store_chain="S-KAUPAT",
        purchase_date=None,
        lines=[ExtractedLine(name="KEVYTMAITOJUOMA", quantity=2)],
    )

    with (
        patch(OCR, new_callable=AsyncMock, return_value="S-KAUPAT text"),
        patch(TEXT, new_callable=AsyncMock, return_value=extraction),
    ):
        await ReceiptWorker(telegram, session_factory).run_job(job)

    assert len(telegram.edited) == 1
    chat_id, message_id, text = telegram.edited[0]
    assert (chat_id, message_id) == (1001, 55)
    assert text.startswith("S-group, date not read: 1 item, 0 matched.")
    assert "New: KEVYTMAITOJUOMA" in text


async def test_processing_failure_edits_the_message_with_the_failure(
    db_session, session_factory
):
    job = await _job(db_session)
    telegram = FakeTelegram()

    with (
        patch(OCR, new_callable=AsyncMock, return_value="text"),
        patch(
            TEXT, new_callable=AsyncMock, side_effect=LLMExtractionError("timed out")
        ),
    ):
        await ReceiptWorker(telegram, session_factory).run_job(job)

    assert telegram.edited[0][2].startswith("Could not read this receipt")


async def test_unexpected_error_still_answers(db_session, session_factory):
    job = await _job(db_session)
    telegram = FakeTelegram()

    with patch(
        "app.telegram_bot.worker.ReceiptProcessingService.process_receipt",
        side_effect=RuntimeError("boom"),
    ):
        await ReceiptWorker(telegram, session_factory).run_job(job)

    assert telegram.edited[0][2].startswith("Could not read this receipt")


async def test_jobs_run_one_at_a_time(db_session, session_factory):
    first = await _job(db_session, b"%PDF one", 1)
    second = await _job(db_session, b"%PDF two", 2)
    events: list[str] = []
    running = 0

    async def fake_run_job(self, job: Job) -> None:
        nonlocal running
        running += 1
        assert running == 1
        events.append(f"start {job.message_id}")
        await asyncio.sleep(0.01)
        events.append(f"end {job.message_id}")
        running -= 1

    queue: asyncio.Queue[Job] = asyncio.Queue()
    queue.put_nowait(first)
    queue.put_nowait(second)

    with patch.object(ReceiptWorker, "run_job", fake_run_job):
        worker = ReceiptWorker(FakeTelegram(), session_factory)
        task = asyncio.create_task(worker.run(queue))
        await asyncio.wait_for(queue.join(), timeout=2)
        task.cancel()

    assert events == ["start 1", "end 1", "start 2", "end 2"]
