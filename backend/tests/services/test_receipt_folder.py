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
from unittest.mock import patch
from uuid import uuid4

import anyio
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.receipt import Receipt
from app.services import receipt_folder
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


class TestIsolatedFailures:
    """F1: a non-ingest failure (DB down, disk full, ...) on one file must not stop the
    rest of the pass. The two *expected* rejections (wrong type, too large) already have
    their own tests above and are not what this covers."""

    async def test_a_failing_file_does_not_stop_a_second_file_in_the_same_pass(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        (tmp_path / "bad.pdf").write_bytes(PDF)
        (tmp_path / "good.pdf").write_bytes(PDF + b"-distinct")
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)

        real_ingest = receipt_folder.ingest_receipt_file

        async def flaky(db, *, content, filename, content_type):
            if filename == "bad.pdf":
                raise ConnectionError("database restarting")
            return await real_ingest(
                db, content=content, filename=filename, content_type=content_type
            )

        with patch(
            "app.services.receipt_folder.ingest_receipt_file", side_effect=flaky
        ):
            taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert (tmp_path / "bad.pdf").exists()  # left in place, never moved
        assert not (tmp_path / "good.pdf").exists()
        assert (tmp_path / "processed" / "good.pdf").exists()
        assert await _count(db_session) == 1

        # Next pass (fault gone): the file left in place is retried and succeeds.
        taken = await watcher.scan_once(session_factory)
        assert taken == 1
        assert not (tmp_path / "bad.pdf").exists()
        assert (tmp_path / "processed" / "bad.pdf").exists()
        assert await _count(db_session) == 2


class TestSymlinks:
    """F2: never read through a symlink; a planted link must not be followed."""

    async def test_a_symlink_is_ignored_and_never_followed(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        outside = tmp_path.parent / f"outside-{uuid4()}.pdf"
        outside.write_bytes(b"SECRET CONTENT THAT IS NOT A RECEIPT")
        link = tmp_path / "link.pdf"
        link.symlink_to(outside)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)

        for _ in range(3):
            await watcher.scan_once(session_factory)
            clock.advance(SETTLE_SECONDS * 2)

        assert await _count(db_session) == 0
        assert link.is_symlink()  # left alone: not moved, not deleted, not followed

    async def test_a_symlink_is_only_logged_once(self, session_factory, tmp_path: Path):
        outside = tmp_path.parent / f"outside-{uuid4()}.pdf"
        outside.write_bytes(b"irrelevant")
        link = tmp_path / "link.pdf"
        link.symlink_to(outside)
        watcher = _watcher(tmp_path)

        with patch.object(receipt_folder.logger, "warning") as warning:
            for _ in range(3):
                await watcher.scan_once(session_factory)

        symlink_warnings = [
            call
            for call in warning.call_args_list
            if call.kwargs.get("extra", {}).get("dropped_name") == "link.pdf"
        ]
        assert len(symlink_warnings) == 1


class TestArchiveIsAtomic:
    """F3: claiming the archive name must not let a second worker's already-archived
    file be silently overwritten."""

    async def test_two_files_with_the_same_name_both_survive_in_processed(
        self, db_session: AsyncSession, session_factory, tmp_path: Path
    ):
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        # Stands in for another worker having already archived a file under this name.
        (processed_dir / "order.pdf").write_bytes(b"ALREADY ARCHIVED BY ANOTHER WORKER")

        (tmp_path / "order.pdf").write_bytes(PDF)
        clock = _FakeClock()
        watcher = _watcher(tmp_path, clock)
        await watcher.scan_once(session_factory)
        clock.advance(SETTLE_SECONDS)
        taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert (
            processed_dir / "order.pdf"
        ).read_bytes() == b"ALREADY ARCHIVED BY ANOTHER WORKER"
        assert (processed_dir / "order-1.pdf").read_bytes() == PDF


class TestSizeCapBeforeRead:
    """F4: reject by the stat'd size before reading the file's content at all."""

    async def test_oversized_file_is_rejected_without_reading_its_content(
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

        with patch.object(
            anyio.Path,
            "read_bytes",
            side_effect=AssertionError("must not read an oversized file"),
        ):
            taken = await watcher.scan_once(session_factory)

        assert taken == 1
        assert (tmp_path / "rejected" / "huge.pdf").exists()
        assert (tmp_path / "rejected" / "huge.pdf.reason.txt").exists()
        assert await _count(db_session) == 0
