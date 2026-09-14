"""Receipt worker: read queued receipts one at a time (MVP-R3).

The extraction model serves one request at a time and a receipt takes about a minute, so one
worker process reads the Postgres queue sequentially. Uploads from the iPad and the Telegram bot
both land in that queue.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.services import receipt_queue
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.receipt_processing import MAX_ERROR_CHARS, ReceiptProcessingService

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def _mark_crashed(
    session_factory: SessionFactory, receipt_id: UUID, error: str
) -> None:
    async with session_factory() as db:
        receipt: Any = await db.get(Receipt, receipt_id, populate_existing=True)
        if receipt is None:
            return
        receipt.processing_status = ReceiptStatus.FAILED
        receipt.error = error[:MAX_ERROR_CHARS]
        await db.commit()
    await broadcast_receipt_status(receipt_id=receipt_id, status="failed", error=error)


async def run_once(session_factory: SessionFactory) -> bool:
    """Fail stale work, then read the oldest queued receipt. Returns whether one was read."""
    async with session_factory() as db:
        await receipt_queue.fail_stale(db)
        receipt = await receipt_queue.claim_next(db)
        if receipt is None:
            return False
        receipt_id = cast(UUID, receipt.id)

    try:
        async with session_factory() as db:
            claimed = await db.get(Receipt, receipt_id, populate_existing=True)
            if claimed is None:
                return True
            result = await ReceiptProcessingService(db).process_receipt(claimed)
        logger.info(
            "Receipt read",
            extra={"receipt_id": str(receipt_id), "success": result.success},
        )
    except Exception as exc:
        logger.exception(
            "Receipt worker crashed", extra={"receipt_id": str(receipt_id)}
        )
        await _mark_crashed(
            session_factory, receipt_id, f"Receipt processing crashed: {exc}"
        )
    return True


async def run(
    session_factory: SessionFactory,
    poll_seconds: float,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> None:
    """Read the queue forever; wait ``poll_seconds`` only when it is empty or on errors."""
    while True:
        try:
            worked = await run_once(session_factory)
        except Exception:
            # Database restarting and similar: keep the service alive and try again
            logger.exception("Receipt worker loop failed")
            worked = False
        if not worked:
            await sleep(poll_seconds)
