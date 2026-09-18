"""Receipt processing queue kept in Postgres (MVP-R3).

Uploads are queued; one worker service (``python -m app.worker``) claims them in FIFO order and
reads them one at a time, because the extraction model serves a single request at a time. The
queue survives restarts. A receipt stuck in ``processing`` (worker killed, hung call) is failed
after ``RECEIPT_STALE_MINUTES`` so it can be retried.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.services.broadcast_helpers import broadcast_receipt_status

logger = get_logger(__name__)


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def stale_error() -> str:
    return (
        f"Processing did not finish within {settings.RECEIPT_STALE_MINUTES} minutes "
        "(worker restarted or stuck)"
    )


class NotEnqueueable(Exception):
    """The receipt left the state the caller saw before the queue write landed."""


# A freshly ingested receipt is the only thing the upload path may queue.
ENQUEUEABLE_ON_UPLOAD = (ReceiptStatus.UPLOADED,)
# Re-reading is allowed from any state the pipeline has finished with, but never
# from `confirmed`: the cook has already turned that receipt into inventory.
ENQUEUEABLE_ON_REREAD = (
    ReceiptStatus.UPLOADED,
    ReceiptStatus.COMPLETED,
    ReceiptStatus.FAILED,
)


async def enqueue(
    db: AsyncSession,
    receipt: Receipt,
    *,
    allowed_statuses: Sequence[str] = ENQUEUEABLE_ON_REREAD,
    now: datetime | None = None,
) -> Receipt:
    """Put a receipt at the back of the queue, clearing any previous failure.

    A conditional UPDATE, not an attribute write: the caller read the status in a
    separate statement, and `confirm_receipt` holds a row lock while it sets
    `confirmed`. Without the WHERE clause, `/process` could block on that lock and
    then land `queued` on top of `confirmed`, so the cook's confirmed receipt went
    back through the reader.

    Raises:
        NotEnqueueable: the row is no longer in one of ``allowed_statuses``.
    """
    receipt_id = cast(UUID, receipt.id)
    queued_at = _now(now)
    updated = (
        await db.execute(
            update(Receipt)
            .where(
                Receipt.id == receipt_id,
                Receipt.processing_status.in_(list(allowed_statuses)),
            )
            .values(
                processing_status=ReceiptStatus.QUEUED,
                queued_at=queued_at,
                processing_started_at=None,
                error=None,
            )
            .returning(Receipt.id)
        )
    ).scalar_one_or_none()

    if updated is None:
        # Nothing was written, so there is nothing to roll back; the caller's
        # transaction is left exactly as it was.
        current = await db.get(Receipt, receipt_id, populate_existing=True)
        found = getattr(current, "processing_status", None) or "gone"
        raise NotEnqueueable(f"Receipt is {found} and cannot be queued")

    await db.commit()
    # The caller holds this object; refresh it rather than hand back a stale status.
    await db.get(Receipt, receipt_id, populate_existing=True)
    await broadcast_receipt_status(receipt_id=receipt_id, status="queued")
    logger.info("Receipt queued", extra={"receipt_id": str(receipt_id)})
    return receipt


async def claim_next(
    db: AsyncSession, *, now: datetime | None = None
) -> Receipt | None:
    """Mark the oldest queued receipt ``processing`` and return it; None when the queue is empty.

    ``SKIP LOCKED`` lets concurrent claimers pass over a row another one is taking.
    """
    oldest = (
        select(Receipt.id)
        .where(Receipt.processing_status == ReceiptStatus.QUEUED)
        .order_by(Receipt.queued_at.asc().nulls_first(), Receipt.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    claimed_id = (
        await db.execute(
            update(Receipt)
            .where(Receipt.id == oldest)
            .values(
                processing_status=ReceiptStatus.PROCESSING,
                processing_started_at=_now(now),
                error=None,
            )
            .returning(Receipt.id)
        )
    ).scalar_one_or_none()
    await db.commit()
    if claimed_id is None:
        return None

    receipt = await db.get(Receipt, claimed_id, populate_existing=True)
    await broadcast_receipt_status(receipt_id=claimed_id, status="processing")
    logger.info("Receipt claimed", extra={"receipt_id": str(claimed_id)})
    return receipt


async def fail_stale(db: AsyncSession, *, now: datetime | None = None) -> int:
    """Fail receipts that have been ``processing`` longer than the stale limit."""
    cutoff = _now(now) - timedelta(minutes=settings.RECEIPT_STALE_MINUTES)
    stale_ids = list(
        (
            await db.execute(
                update(Receipt)
                .where(
                    Receipt.processing_status == ReceiptStatus.PROCESSING,
                    Receipt.processing_started_at < cutoff,
                )
                .values(processing_status=ReceiptStatus.FAILED, error=stale_error())
                .returning(Receipt.id)
            )
        )
        .scalars()
        .all()
    )
    await db.commit()
    if not stale_ids:
        return 0

    # Loaded objects in this session must not keep the old status
    for receipt_id in stale_ids:
        await db.get(Receipt, receipt_id, populate_existing=True)
        await broadcast_receipt_status(
            receipt_id=receipt_id, status="failed", error=stale_error()
        )
    logger.warning(
        "Stale receipts failed",
        extra={"count": len(stale_ids), "receipt_ids": [str(i) for i in stale_ids]},
    )
    return len(stale_ids)


async def queue_position(db: AsyncSession, receipt: Receipt) -> int:
    """How many queued or processing receipts are ahead of this one."""
    if receipt.queued_at is None:
        return 0
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(Receipt)
                .where(
                    Receipt.processing_status.in_(
                        [ReceiptStatus.QUEUED, ReceiptStatus.PROCESSING]
                    ),
                    Receipt.queued_at < receipt.queued_at,
                    Receipt.id != receipt.id,
                )
            )
        ).scalar_one()
    )
