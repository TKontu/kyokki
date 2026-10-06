"""Which Telegram chat is told about which receipt, and whether it has been (CL5).

The bot's result notifier used to keep this in memory, so a restart while a receipt was being
read lost the edit of its "Received" message. A row is written when the bot acknowledges an
upload (``message_id`` is that acknowledgement) or when it finds a receipt that arrived some
other way (e-mail, the watched folder; ``message_id`` is empty and a new message is sent).
``notified_at`` is set once the result has reached the chat; until then the row is pending.
"""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db.base_class import Base


class TelegramReceiptMessage(Base):  # type: ignore[misc]  # Base is untyped until H21
    """One chat's result message for one receipt."""

    __tablename__ = "telegram_receipt_message"

    receipt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receipt.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Telegram chat ids exceed 32 bits (supergroups are -100xxxxxxxxxx)
    chat_id = Column(BigInteger, primary_key=True)
    # The acknowledgement to edit; empty when the result goes out as a new message
    message_id = Column(BigInteger, nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TelegramReceiptMessage {self.receipt_id} chat={self.chat_id}>"
