"""Data access on `telegram_receipt_message`: the bot's durable list of results to deliver (CL5).

The callers commit. A row with ``notified_at`` empty is a result still owed to that chat.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.models.telegram_receipt_message import TelegramReceiptMessage
from app.schemas.receipt import ReceiptStatus

# The statuses the notifier reports: the receipt has been read, or reading it failed
FINISHED_STATUSES = (
    ReceiptStatus.COMPLETED,
    ReceiptStatus.CONFIRMED,
    ReceiptStatus.FAILED,
)

DEFAULT_DISCOVERY_LIMIT = 20


async def watch(
    db: AsyncSession, receipt_id: UUID, chat_id: int, message_id: int
) -> None:
    """Owe ``chat_id`` the result of ``receipt_id``, by editing ``message_id``."""
    statement = insert(TelegramReceiptMessage).values(
        receipt_id=receipt_id,
        chat_id=chat_id,
        message_id=message_id,
        notified_at=None,
        created_at=datetime.now(UTC),
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=["receipt_id", "chat_id"],
            set_={"message_id": message_id, "notified_at": None},
        )
    )


async def claim_for_chats(
    db: AsyncSession, receipt_id: UUID, chat_ids: Iterable[int]
) -> None:
    """Owe each chat the result of a receipt that arrived without the bot; new messages."""
    now = datetime.now(UTC)
    values = [
        {"receipt_id": receipt_id, "chat_id": chat_id, "created_at": now}
        for chat_id in chat_ids
    ]
    if not values:
        return
    await db.execute(
        insert(TelegramReceiptMessage)
        .values(values)
        .on_conflict_do_nothing(index_elements=["receipt_id", "chat_id"])
    )


@dataclass(frozen=True)
class Owed:
    """A result still owed to a chat; ``message_id`` None means send a new message."""

    receipt_id: UUID
    chat_id: int
    message_id: int | None


async def unnotified(db: AsyncSession) -> list[Owed]:
    """Every result still owed, oldest first."""
    result = await db.execute(
        select(
            TelegramReceiptMessage.receipt_id,
            TelegramReceiptMessage.chat_id,
            TelegramReceiptMessage.message_id,
        )
        .where(TelegramReceiptMessage.notified_at.is_(None))
        .order_by(TelegramReceiptMessage.created_at)
    )
    return [
        Owed(receipt_id=receipt_id, chat_id=chat_id, message_id=message_id)
        for receipt_id, chat_id, message_id in result.all()
    ]


async def mark_notified(db: AsyncSession, receipt_id: UUID, chat_id: int) -> None:
    """The result reached the chat. A row already gone with its receipt is fine."""
    await db.execute(
        update(TelegramReceiptMessage)
        .where(
            TelegramReceiptMessage.receipt_id == receipt_id,
            TelegramReceiptMessage.chat_id == chat_id,
        )
        .values(notified_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


async def unannounced_finished_receipt_ids(
    db: AsyncSession, *, since: datetime, limit: int = DEFAULT_DISCOVERY_LIMIT
) -> list[UUID]:
    """Finished receipts created at or after ``since`` that no chat has a row for.

    These arrived by e-mail or the watched folder; a receipt sent to the bot has its
    acknowledgement's row. Oldest first, at most ``limit``.
    """
    has_row = exists().where(TelegramReceiptMessage.receipt_id == Receipt.id)
    result = await db.scalars(
        select(Receipt.id)
        .where(
            Receipt.processing_status.in_([str(s) for s in FINISHED_STATUSES]),
            Receipt.created_at >= since,
            ~has_row,
        )
        .order_by(Receipt.created_at)
        .limit(limit)
    )
    return list(result.all())
