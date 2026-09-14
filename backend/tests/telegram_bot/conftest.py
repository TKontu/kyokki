"""Fakes shared by the Telegram bot tests."""

import shutil
from contextlib import asynccontextmanager

import anyio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


class FakeTelegram:
    """Records calls instead of talking to Telegram; serves files from a dict."""

    def __init__(self, files: dict[str, tuple[bytes, int]] | None = None):
        self.files = files or {}
        self.sent: list[tuple[int, str]] = []
        self.edited: list[tuple[int, int, str]] = []
        self.downloads: list[str] = []
        self._next_message_id = 100

    async def send_message(self, chat_id: int, text: str) -> int:
        self.sent.append((chat_id, text))
        self._next_message_id += 1
        return self._next_message_id

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        self.edited.append((chat_id, message_id, text))

    async def get_file(self, file_id: str) -> dict:
        content, size = self.files[file_id]
        return {"file_path": f"path/{file_id}", "file_size": size}

    async def download_file(self, file_path: str) -> bytes:
        self.downloads.append(file_path)
        return self.files[file_path.removeprefix("path/")][0]


@pytest.fixture
def session_factory(db_session: AsyncSession):
    """A session factory that hands out the test session without closing it."""

    @asynccontextmanager
    async def factory():
        yield db_session

    return factory


@pytest.fixture(autouse=True)
async def _clean_receipt_files():
    yield
    receipts_dir = anyio.Path("data/receipts")
    if await receipts_dir.exists():
        shutil.rmtree(str(receipts_dir))
