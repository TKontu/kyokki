"""Watched folder receipt drop-in (A2): files dropped on disk are read like uploads.

A phone or computer sync app (Syncthing, a network share, e-receipts saved from mail) drops
PDFs and photos into ``RECEIPT_WATCH_DIR`` instead of going through the iPad upload API or the
Telegram bot. ``ReceiptFolderWatcher`` turns each settled file into a queued receipt through the
same ``receipt_ingest`` path (validation, duplicate check), then files it under processed/,
duplicates/ or rejected/ so nothing is read twice and nothing is read half-written.
"""

import hashlib
import shutil
from pathlib import Path

import anyio
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.receipt import Receipt
from app.services.receipt_folder import ReceiptFolderWatcher

PDF = b"%PDF-1.4 fake S-kaupat order receipt"
SETTLE_SECONDS = 5.0


@pytest.fixture(autouse=True)
async def _clean_receipt_files():
    yield
    receipts_dir = anyio.Path("data/receipts")
    if await receipts_dir.exists():
        shutil.rmtree(str(receipts_dir))


class _FakeClock:
    """A controllable clock so settling does not need a real sleep in tests."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _watcher(watch_dir: Path, clock: _FakeClock | None = None) -> ReceiptFolderWatcher:
    return ReceiptFolderWatcher(
        watch_dir, settle_seconds=SETTLE_SECONDS, clock=clock or _FakeClock()
    )


async def _count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Receipt))).scalar_one()


class TestSettledFileBecomesAReceipt:
    async def test_pdf_is_queued_and_moved_to_processed(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        (tmp_path / "order.pdf").write_bytes(PDF)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)

        # First pass only notices the file; it has not settled yet.
        taken = await watcher.scan_once(session_factory)
        assert taken == 0
        assert (tmp_path / "order.pdf").exists()
        assert await _count(db_session) == 0

        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert not (tmp_path / "order.pdf").exists()
        assert (tmp_path / "processed" / "order.pdf").exists()
        assert (tmp_path / "processed" / "order.pdf").read_bytes() == PDF

        receipt = (await db_session.execute(select(Receipt))).scalar_one()
        assert receipt.content_sha256 == hashlib.sha256(PDF).hexdigest()
        assert receipt.processing_status == "queued"

    async def test_a_second_copy_goes_to_duplicates(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        (tmp_path / "order.pdf").write_bytes(PDF)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        await watcher.scan_once(session_factory)

        (tmp_path / "kuitti (1).pdf").write_bytes(PDF)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert not (tmp_path / "kuitti (1).pdf").exists()
        assert (tmp_path / "duplicates" / "kuitti (1).pdf").exists()
        assert await _count(db_session) == 1


class TestRejection:
    async def test_wrong_type_is_rejected_with_a_reason_file(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        (tmp_path / "note.txt").write_text("not a receipt")
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert not (tmp_path / "note.txt").exists()
        assert (tmp_path / "rejected" / "note.txt").exists()
        reason = (tmp_path / "rejected" / "note.txt.reason.txt").read_text()
        assert reason.strip()
        assert await _count(db_session) == 0

    async def test_oversized_file_is_rejected(
        self,
        db_session: AsyncSession,
        session_factory,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(settings, "MAX_RECEIPT_UPLOAD_BYTES", 8)
        (tmp_path / "huge.pdf").write_bytes(PDF)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert (tmp_path / "rejected" / "huge.pdf").exists()
        assert (tmp_path / "rejected" / "huge.pdf.reason.txt").exists()
        assert await _count(db_session) == 0


class TestSettling:
    async def test_a_file_still_growing_is_not_taken(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        target = tmp_path / "order.pdf"
        target.write_bytes(b"%PDF partial")
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)

        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        # The sync wrote more bytes just before this poll: still not settled.
        target.write_bytes(b"%PDF partial plus more bytes written mid-sync")
        taken = await watcher.scan_once(session_factory)
        assert taken == 0
        assert target.exists()
        assert await _count(db_session) == 0

        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)
        assert taken == 1
        assert not target.exists()
        assert await _count(db_session) == 1

    async def test_never_read_twice(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        (tmp_path / "order.pdf").write_bytes(PDF)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        await watcher.scan_once(session_factory)

        # Nothing left in the watched root to pick up again; scanning more does nothing.
        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)
        assert taken == 0
        assert await _count(db_session) == 1


class TestIgnoredNames:
    async def test_dotfiles_and_temp_suffixes_are_never_taken(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        ignored_names = [
            ".hidden.pdf",
            "order.pdf.part",
            "order.pdf.tmp",
            "order.pdf~",
            ".syncthing.order.pdf.tmp",
        ]
        for name in ignored_names:
            (tmp_path / name).write_bytes(PDF)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)

        for _ in range(3):
            await watcher.scan_once(session_factory)
            clock.advance(SETTLE_SECONDS * 2)

        assert await _count(db_session) == 0
        for name in ignored_names:
            assert (tmp_path / name).exists()


class TestMissingDirectory:
    async def test_a_missing_watch_dir_does_not_raise(
        self, session_factory, tmp_path: Path
    ):
        watcher = _watcher(tmp_path / "does-not-exist")
        taken = await watcher.scan_once(session_factory)
        assert taken == 0
