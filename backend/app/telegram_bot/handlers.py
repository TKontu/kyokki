"""Turn one Telegram update into a reply and a receipt queued for the worker service."""

from collections.abc import Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.receipt import ReceiptResponse
from app.services import receipt_queue
from app.services.receipt_ingest import (
    ALLOWED_CONTENT_TYPES,
    UnsupportedReceiptType,
    ingest_receipt_file,
)
from app.telegram_bot import messages
from app.telegram_bot.client import MAX_FILE_BYTES, TelegramError

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class BotApi(Protocol):
    async def send_message(self, chat_id: int, text: str) -> int: ...

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str
    ) -> None: ...

    async def get_file(self, file_id: str) -> dict[str, Any]: ...

    async def download_file(self, file_path: str) -> bytes: ...


class Notifier(Protocol):
    def watch(self, receipt_id: UUID, chat_id: int, message_id: int) -> None: ...


@dataclass(frozen=True)
class _IncomingFile:
    file_id: str
    filename: str
    content_type: str
    size: int | None


class BotHandler:
    def __init__(
        self,
        client: BotApi,
        session_factory: SessionFactory,
        notifier: Notifier,
        allowed_chat_ids: Iterable[int],
    ):
        self.client = client
        self.session_factory = session_factory
        self.notifier = notifier
        self.allowed_chat_ids = frozenset(allowed_chat_ids)

    async def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat_id = (message.get("chat") or {}).get("id")
        if not isinstance(chat_id, int):
            return
        text = (message.get("text") or "").strip()

        if chat_id not in self.allowed_chat_ids:
            # Log the id only: never the content of a stranger's message
            logger.warning(
                "Message from a chat not in the allowlist", extra={"chat_id": chat_id}
            )
            if text.startswith("/start"):
                await self.client.send_message(
                    chat_id, messages.unknown_chat_text(chat_id)
                )
            return

        incoming = _incoming_file(message)
        if incoming is None:
            await self.client.send_message(chat_id, messages.help_text())
            return
        await self._receive(chat_id, incoming)

    async def _receive(self, chat_id: int, incoming: _IncomingFile) -> None:
        if incoming.content_type not in ALLOWED_CONTENT_TYPES:
            await self.client.send_message(chat_id, messages.unsupported_text())
            return
        if incoming.size is not None and incoming.size > MAX_FILE_BYTES:
            await self.client.send_message(chat_id, messages.too_large_text())
            return

        try:
            info = await self.client.get_file(incoming.file_id)
            if int(info.get("file_size") or 0) > MAX_FILE_BYTES:
                await self.client.send_message(chat_id, messages.too_large_text())
                return
            content = await self.client.download_file(str(info["file_path"]))
        except (TelegramError, KeyError) as exc:
            logger.warning(
                "Receipt download failed", extra={"chat_id": chat_id, "error": str(exc)}
            )
            await self.client.send_message(chat_id, messages.download_failed_text())
            return

        async with self.session_factory() as db:
            try:
                result = await ingest_receipt_file(
                    db,
                    content=content,
                    filename=incoming.filename,
                    content_type=incoming.content_type,
                )
            except UnsupportedReceiptType:
                await self.client.send_message(chat_id, messages.unsupported_text())
                return
            receipt = ReceiptResponse.model_validate(result.receipt)
            ahead = (
                0
                if result.duplicate
                else await receipt_queue.queue_position(db, result.receipt)
            )

        if result.duplicate:
            logger.info(
                "Duplicate receipt from Telegram", extra={"receipt_id": str(receipt.id)}
            )
            await self.client.send_message(chat_id, messages.duplicate_text(receipt))
            return

        message_id = await self.client.send_message(
            chat_id, messages.received_text(ahead)
        )
        # The worker service reads it from the queue; the notifier edits the acknowledgement
        self.notifier.watch(receipt.id, chat_id, message_id)
        logger.info(
            "Receipt received from Telegram",
            extra={"receipt_id": str(receipt.id), "queued_ahead": ahead},
        )


def _incoming_file(message: dict[str, Any]) -> _IncomingFile | None:
    document = message.get("document")
    if isinstance(document, dict) and document.get("file_id"):
        return _IncomingFile(
            file_id=str(document["file_id"]),
            filename=str(
                document.get("file_name")
                or f"telegram-{document.get('file_unique_id')}"
            ),
            content_type=str(document.get("mime_type") or ""),
            size=document.get("file_size"),
        )

    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        # Telegram sends several sizes of a compressed photo; OCR wants the largest
        largest = max(
            photos, key=lambda p: (p.get("file_size") or 0, p.get("width") or 0)
        )
        return _IncomingFile(
            file_id=str(largest["file_id"]),
            filename=f"telegram-{largest.get('file_unique_id') or largest['file_id']}.jpg",
            content_type="image/jpeg",
            size=largest.get("file_size"),
        )
    return None
