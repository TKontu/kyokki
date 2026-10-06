"""Tell the allowed chats each receipt's result once the worker service has read it (CL5).

Receipts are read by ``python -m app.worker`` from the Postgres queue (MVP-R3). The bot
records which chat is owed which receipt's result in ``telegram_receipt_message`` and polls
their status:

- A receipt sent to the bot gets a row for that chat pointing at its "Received" message,
  which is edited with the result.
- A receipt that arrived another way (e-mail, the watched folder) and finished reading after
  this process started gets a row per allowed chat, and the result goes out as a new message.
  Receipts from before the start are left alone, so a first deploy does not replay history.

The table is the truth: rows still owed are reloaded on every poll, so a bot restart while a
receipt is being read still delivers its result, and ``notified_at`` keeps it from being
delivered twice. The in-memory map only remembers acknowledgements whose row went away with
a deleted receipt, so that one can still say so.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.crud import telegram_receipt_message as crud_messages
from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptResponse, ReceiptStatus
from app.telegram_bot import messages
from app.telegram_bot.client import TelegramError
from app.telegram_bot.handlers import BotApi, SessionFactory

logger = get_logger(__name__)

DEFAULT_POLL_SECONDS = 3.0
# Receipts from other sources are looked for this far back at most (and never before the
# process started), a bounded number per poll.
DISCOVERY_WINDOW = timedelta(days=1)
DISCOVERY_LIMIT = 20


@dataclass(frozen=True)
class Pending:
    chat_id: int
    # The acknowledgement to edit; None sends the result as a new message
    message_id: int | None


class ResultNotifier:
    def __init__(
        self,
        client: BotApi,
        session_factory: SessionFactory,
        chat_ids: Iterable[int] = (),
        public_url: str | None = None,
        started_at: datetime | None = None,
    ):
        self.client = client
        self.session_factory = session_factory
        self.chat_ids = tuple(chat_ids)
        self.public_url = public_url
        self.started_at = started_at or datetime.now(UTC)
        self.pending: dict[tuple[UUID, int], Pending] = {}

    async def watch(self, receipt_id: UUID, chat_id: int, message_id: int) -> None:
        self.pending[(receipt_id, chat_id)] = Pending(
            chat_id=chat_id, message_id=message_id
        )
        async with self.session_factory() as db:
            await crud_messages.watch(db, receipt_id, chat_id, message_id)
            await db.commit()

    async def _load(self) -> None:
        """Claim newly finished receipts from other sources, then reload what is owed."""
        async with self.session_factory() as db:
            if self.chat_ids:
                since = max(self.started_at, datetime.now(UTC) - DISCOVERY_WINDOW)
                found = await crud_messages.unannounced_finished_receipt_ids(
                    db, since=since, limit=DISCOVERY_LIMIT
                )
                for receipt_id in found:
                    await crud_messages.claim_for_chats(db, receipt_id, self.chat_ids)
                if found:
                    await db.commit()
                    logger.info(
                        "Receipts from other sources to report",
                        extra={"receipts": len(found)},
                    )
            for row in await crud_messages.unnotified(db):
                self.pending.setdefault(
                    (row.receipt_id, row.chat_id),
                    Pending(chat_id=row.chat_id, message_id=row.message_id),
                )

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
            text = messages.result_text(response)
        elif response.processing_status == ReceiptStatus.FAILED:
            # The raw reason can carry gateway/model internals; it goes only to the log
            # (never the image), and the cook gets a short, generic sentence instead.
            logger.info(
                "Receipt failed, replying without the internal reason",
                extra={"receipt_id": str(receipt_id), "reason": response.error},
            )
            text = messages.failure_text(response.error)
        else:
            return None
        return messages.with_review_link(text, self.public_url, receipt_id)

    async def _reply(self, target: Pending, text: str) -> None:
        if target.message_id is None:
            await self.client.send_message(target.chat_id, text)
            return
        try:
            await self.client.edit_message_text(target.chat_id, target.message_id, text)
        except TelegramError as exc:
            # The acknowledgement may be gone; send the result as a new message instead
            logger.warning(
                "Could not edit the acknowledgement", extra={"error": str(exc)}
            )
            await self.client.send_message(target.chat_id, text)

    async def check_once(self) -> int:
        """Answer every finished receipt; returns how many messages were delivered."""
        await self._load()
        answered = 0
        texts: dict[UUID, str | None] = {}
        for key, target in list(self.pending.items()):
            receipt_id = key[0]
            if receipt_id not in texts:
                texts[receipt_id] = await self._text_for(receipt_id)
            text = texts[receipt_id]
            if text is None:
                continue
            try:
                await self._reply(target, text)
            except TelegramError as exc:
                # Stays owed and is retried on the next poll; other chats still get theirs
                logger.warning(
                    "Could not deliver the result",
                    extra={"chat_id": target.chat_id, "error": str(exc)},
                )
                continue
            async with self.session_factory() as db:
                await crud_messages.mark_notified(db, receipt_id, target.chat_id)
                await db.commit()
            del self.pending[key]
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
