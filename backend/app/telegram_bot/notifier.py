"""Edit each "Received" acknowledgement once the worker service has read the receipt.

Receipts are read by ``python -m app.worker`` from the Postgres queue (MVP-R3). The bot only
remembers which message belongs to which receipt and polls their status. That map is in memory:
after a bot restart the receipts are still read, but the old acknowledgements are not edited.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptResponse, ReceiptStatus
from app.telegram_bot import messages
from app.telegram_bot.client import TelegramError
from app.telegram_bot.handlers import BotApi, SessionFactory

logger = get_logger(__name__)

DEFAULT_POLL_SECONDS = 3.0


@dataclass(frozen=True)
class Pending:
    chat_id: int
    message_id: int


class ResultNotifier:
    def __init__(self, client: BotApi, session_factory: SessionFactory):
        self.client = client
        self.session_factory = session_factory
        self.pending: dict[UUID, Pending] = {}

    def watch(self, receipt_id: UUID, chat_id: int, message_id: int) -> None:
        self.pending[receipt_id] = Pending(chat_id=chat_id, message_id=message_id)

    async def _text_for(self, receipt_id: UUID) -> str | None:
        """The reply once the receipt is finished; None while it is queued or processing."""
        async with self.session_factory() as db:
            receipt = await db.get(Receipt, receipt_id, populate_existing=True)
            if receipt is None:
                return messages.failure_text("the receipt was deleted")
            response = ReceiptResponse.model_validate(receipt)
        if response.processing_status in (
            ReceiptStatus.COMPLETED,
            ReceiptStatus.CONFIRMED,
        ):
            return messages.result_text(response)
        if response.processing_status == ReceiptStatus.FAILED:
            return messages.failure_text(response.error)
        return None

    async def _reply(self, target: Pending, text: str) -> None:
        try:
            await self.client.edit_message_text(target.chat_id, target.message_id, text)
        except TelegramError as exc:
            # The acknowledgement may be gone; send the result as a new message instead
            logger.warning(
                "Could not edit the acknowledgement", extra={"error": str(exc)}
            )
            await self.client.send_message(target.chat_id, text)

    async def check_once(self) -> int:
        """Answer every finished receipt; returns how many were answered."""
        answered = 0
        for receipt_id, target in list(self.pending.items()):
            text = await self._text_for(receipt_id)
            if text is None:
                continue
            await self._reply(target, text)
            del self.pending[receipt_id]
            answered += 1
        return answered

    async def run(
        self,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        while True:
            try:
                await self.check_once()
            except Exception:
                logger.exception("Telegram result check failed")
            await sleep(poll_seconds)
