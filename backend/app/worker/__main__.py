"""``python -m app.worker``: read queued receipts until stopped."""

from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.service_runner import run_service
from app.db.session import AsyncSessionLocal
from app.services.receipt_folder import ReceiptFolderWatcher
from app.services.receipt_mail import build_mail_poller
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

    # build_mail_poller logs the disabled/refused cases itself (INFO/ERROR); only the
    # enabled case is logged here, and never the password.
    mail_poller = build_mail_poller(settings)
    if mail_poller is not None:
        logger.info(
            "E-mail receipt poll enabled",
            extra={
                "host": settings.RECEIPT_MAIL_HOST,
                "folder": settings.RECEIPT_MAIL_FOLDER,
                "poll_seconds": settings.RECEIPT_MAIL_POLL_SECONDS,
            },
        )

    await receipt_worker.run(
        AsyncSessionLocal,
        settings.RECEIPT_WORKER_POLL_SECONDS,
        folder_watcher=folder_watcher,
        folder_poll_seconds=settings.RECEIPT_WATCH_POLL_SECONDS,
        mail_poller=mail_poller,
        mail_poll_seconds=settings.RECEIPT_MAIL_POLL_SECONDS,
    )


setup_logging()
run_service(_serve, "Receipt worker")
