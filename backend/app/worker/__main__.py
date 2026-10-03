"""``python -m app.worker``: read queued receipts until stopped."""

from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.service_runner import run_service
from app.db.session import AsyncSessionLocal
from app.services.receipt_folder import ReceiptFolderWatcher
from app.worker import receipt_worker

logger = get_logger(__name__)


async def _serve() -> None:
    logger.info(
        "Receipt worker started",
        extra={
            "poll_seconds": settings.RECEIPT_WORKER_POLL_SECONDS,
            "stale_minutes": settings.receipt_stale_minutes,
        },
    )

    folder_watcher = None
    if settings.RECEIPT_WATCH_DIR:
        folder_watcher = ReceiptFolderWatcher(
            Path(settings.RECEIPT_WATCH_DIR),
            settle_seconds=settings.RECEIPT_WATCH_SETTLE_SECONDS,
        )
        logger.info(
            "Watched receipt folder enabled",
            extra={
                "watch_dir": settings.RECEIPT_WATCH_DIR,
                "poll_seconds": settings.RECEIPT_WATCH_POLL_SECONDS,
                "settle_seconds": settings.RECEIPT_WATCH_SETTLE_SECONDS,
            },
        )
    else:
        logger.info("Watched receipt folder disabled (RECEIPT_WATCH_DIR is empty)")

    await receipt_worker.run(
        AsyncSessionLocal,
        settings.RECEIPT_WORKER_POLL_SECONDS,
        folder_watcher=folder_watcher,
        folder_poll_seconds=settings.RECEIPT_WATCH_POLL_SECONDS,
    )


setup_logging()
run_service(_serve, "Receipt worker")
