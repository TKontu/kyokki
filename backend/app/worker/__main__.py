"""``python -m app.worker``: read queued receipts until stopped."""

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.service_runner import run_service
from app.db.session import AsyncSessionLocal
from app.worker import receipt_worker

logger = get_logger(__name__)


async def _serve() -> None:
    logger.info(
        "Receipt worker started",
        extra={
            "poll_seconds": settings.RECEIPT_WORKER_POLL_SECONDS,
            "stale_minutes": settings.RECEIPT_STALE_MINUTES,
        },
    )
    await receipt_worker.run(AsyncSessionLocal, settings.RECEIPT_WORKER_POLL_SECONDS)


setup_logging()
run_service(_serve, "Receipt worker")
