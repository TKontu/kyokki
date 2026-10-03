"""Receipt worker: read queued receipts one at a time (MVP-R3).

The extraction model serves one request at a time and a receipt takes about a minute, so one
worker process reads the Postgres queue sequentially. Uploads from the iPad and the Telegram bot
both land in that queue.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from time import monotonic
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.services import receipt_queue
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.receipt_folder import ReceiptFolderWatcher
from app.services.receipt_mail import ReceiptMailPoller
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
    *,
    folder_watcher: ReceiptFolderWatcher | None = None,
    folder_poll_seconds: float = 10.0,
    mail_poller: ReceiptMailPoller | None = None,
    mail_poll_seconds: float = 300.0,
    clock: Callable[[], float] = monotonic,
) -> None:
    """Read the queue forever; wait ``poll_seconds`` only when it is empty or on errors.

    Between claims, also scans the watched folder (RECEIPT_WATCH_DIR) when
    ``folder_watcher`` is given, and polls the mailbox (RECEIPT_MAIL_HOST) when
    ``mail_poller`` is given - each at most once every own its poll interval, independent of
    the queue's own pace and of each other, so a slow queue does not starve either scan and a
    busy queue does not scan or poll on every single claim. Either is ``None`` (no scan/poll
    at all) when its setting is empty (or, for mail, refused for lacking an allowlist).
    """
    last_folder_scan = float("-inf")
    last_mail_poll = float("-inf")
    while True:
        if folder_watcher is not None:
            now = clock()
            if now - last_folder_scan >= folder_poll_seconds:
                try:
                    await folder_watcher.scan_once(session_factory)
                except Exception:
                    logger.exception("Receipt folder scan failed")
                last_folder_scan = now

        if mail_poller is not None:
            now = clock()
            if now - last_mail_poll >= mail_poll_seconds:
                try:
                    await mail_poller.poll_once(session_factory)
                except Exception:
                    logger.exception("E-mail receipt poll failed")
                last_mail_poll = now

        try:
            worked = await run_once(session_factory)
        except Exception:
            # Database restarting and similar: keep the service alive and try again
            logger.exception("Receipt worker loop failed")
            worked = False
        if not worked:
            await sleep(poll_seconds)
