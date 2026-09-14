"""One Telegram update in, the right reply and ingest out."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptStatus
from app.telegram_bot import messages
from app.telegram_bot.client import TelegramError
from app.telegram_bot.handlers import BotHandler

from .conftest import FakeTelegram

ALLOWED = 1001
STRANGER = 2002
PDF = b"%PDF-1.4 S-kaupat order"


def _update(chat_id: int, **message) -> dict:
    return {
        "update_id": 1,
        "message": {"message_id": 7, "chat": {"id": chat_id}, **message},
    }


def _document(file_id: str = "doc-1", mime: str = "application/pdf", size: int = 100):
    return {
        "file_id": file_id,
        "file_unique_id": f"u-{file_id}",
        "file_name": "tilaus.pdf",
        "mime_type": mime,
        "file_size": size,
    }


class FakeNotifier:
    """Records which acknowledgements the handler asked to update later."""

    def __init__(self):
        self.watched: list[tuple] = []

    def watch(self, receipt_id, chat_id: int, message_id: int) -> None:
        self.watched.append((receipt_id, chat_id, message_id))

    def empty(self) -> bool:
        return not self.watched


def _handler(
    telegram: FakeTelegram, session_factory
) -> tuple[BotHandler, FakeNotifier]:
    notifier = FakeNotifier()
    handler = BotHandler(
        client=telegram,
        session_factory=session_factory,
        notifier=notifier,
        allowed_chat_ids=[ALLOWED],
    )
    return handler, notifier


async def _receipt_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Receipt))).scalar_one()


class TestAccess:
    async def test_unknown_chat_start_replies_with_the_chat_id(self, session_factory):
        telegram = FakeTelegram()
        handler, _ = _handler(telegram, session_factory)

        await handler.handle_update(_update(STRANGER, text="/start"))

        assert telegram.sent == [(STRANGER, messages.unknown_chat_text(STRANGER))]

    async def test_unknown_chat_file_is_ignored(self, session_factory, db_session):
        telegram = FakeTelegram({"doc-1": (PDF, len(PDF))})
        handler, queue = _handler(telegram, session_factory)

        await handler.handle_update(_update(STRANGER, document=_document()))

        assert telegram.sent == []
        assert telegram.downloads == []
        assert queue.empty()
        assert await _receipt_count(db_session) == 0

    async def test_update_without_a_message_is_ignored(self, session_factory):
        telegram = FakeTelegram()
        handler, _ = _handler(telegram, session_factory)

        await handler.handle_update({"update_id": 3, "edited_message": {}})

        assert telegram.sent == []

    async def test_allowed_help_and_plain_text_get_the_help(self, session_factory):
        telegram = FakeTelegram()
        handler, _ = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, text="/help"))
        await handler.handle_update(_update(ALLOWED, text="hello"))

        assert telegram.sent == [
            (ALLOWED, messages.help_text()),
            (ALLOWED, messages.help_text()),
        ]


class TestFiles:
    async def test_pdf_is_ingested_acknowledged_and_queued(
        self, session_factory, db_session
    ):
        telegram = FakeTelegram({"doc-1": (PDF, len(PDF))})
        handler, queue = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, document=_document()))

        receipt = (await db_session.execute(select(Receipt))).scalar_one()
        assert receipt.image_path.endswith(".pdf")
        # The worker service reads it from the database queue (MVP-R3)
        assert receipt.processing_status == ReceiptStatus.QUEUED
        assert telegram.sent == [(ALLOWED, messages.received_text(0))]
        assert queue.watched == [(receipt.id, ALLOWED, 101)]

    async def test_queue_position_comes_from_the_database(
        self, session_factory, db_session
    ):
        db_session.add(
            Receipt(
                id=uuid4(),
                image_path="data/receipts/other.pdf",
                processing_status=ReceiptStatus.PROCESSING,
                queued_at=datetime.now(UTC) - timedelta(minutes=1),
                processing_started_at=datetime.now(UTC),
                items_extracted=0,
                items_matched=0,
            )
        )
        await db_session.commit()
        telegram = FakeTelegram({"doc-1": (PDF, len(PDF))})
        handler, _ = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, document=_document("doc-1")))

        assert telegram.sent == [(ALLOWED, messages.received_text(1))]

    async def test_queue_position_is_reported(self, session_factory):
        telegram = FakeTelegram(
            {"doc-1": (PDF, len(PDF)), "doc-2": (PDF + b"2", len(PDF) + 1)}
        )
        handler, _ = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, document=_document("doc-1")))
        await handler.handle_update(_update(ALLOWED, document=_document("doc-2")))

        assert telegram.sent[1] == (ALLOWED, messages.received_text(1))

    async def test_photo_uses_the_largest_size(self, session_factory, db_session):
        telegram = FakeTelegram(
            {"small": (b"small jpeg", 10), "large": (b"large jpeg", 900)}
        )
        handler, queue = _handler(telegram, session_factory)
        photo = [
            {"file_id": "small", "file_unique_id": "s", "width": 90, "file_size": 10},
            {
                "file_id": "large",
                "file_unique_id": "l",
                "width": 1080,
                "file_size": 900,
            },
        ]

        await handler.handle_update(_update(ALLOWED, photo=photo))

        assert telegram.downloads == ["path/large"]
        receipt = (await db_session.execute(select(Receipt))).scalar_one()
        assert receipt.image_path.endswith(".jpg")
        assert not queue.empty()

    async def test_unsupported_document_is_refused(self, session_factory, db_session):
        telegram = FakeTelegram({"doc-1": (b"PK zip", 6)})
        handler, queue = _handler(telegram, session_factory)

        await handler.handle_update(
            _update(ALLOWED, document=_document(mime="application/zip"))
        )

        assert telegram.sent == [(ALLOWED, messages.unsupported_text())]
        assert telegram.downloads == []
        assert queue.empty()
        assert await _receipt_count(db_session) == 0

    async def test_too_large_file_is_refused_before_download(
        self, session_factory, db_session
    ):
        size = 25 * 1024 * 1024
        telegram = FakeTelegram({"doc-1": (PDF, size)})
        handler, queue = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, document=_document(size=size)))

        assert telegram.sent == [(ALLOWED, messages.too_large_text())]
        assert telegram.downloads == []
        assert queue.empty()
        assert await _receipt_count(db_session) == 0

    async def test_same_file_twice_is_a_duplicate(self, session_factory, db_session):
        telegram = FakeTelegram(
            {"doc-1": (PDF, len(PDF)), "doc-again": (PDF, len(PDF))}
        )
        handler, queue = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, document=_document("doc-1")))
        await handler.handle_update(_update(ALLOWED, document=_document("doc-again")))

        assert await _receipt_count(db_session) == 1
        assert len(queue.watched) == 1
        assert telegram.sent[1][1].startswith("Already received")

    async def test_download_failure_replies_and_queues_nothing(
        self, session_factory, db_session
    ):
        class Broken(FakeTelegram):
            async def download_file(self, file_path: str) -> bytes:
                raise TelegramError("Telegram download failed")

        telegram = Broken({"doc-1": (PDF, len(PDF))})
        handler, queue = _handler(telegram, session_factory)

        await handler.handle_update(_update(ALLOWED, document=_document()))

        assert telegram.sent[0][1].startswith("Could not download")
        assert queue.empty()
        assert await _receipt_count(db_session) == 0
