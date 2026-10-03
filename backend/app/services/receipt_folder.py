"""Watched folder receipt drop-in: files dropped on disk are read like uploads.

Receipts arrive today by iPad upload (``POST /api/receipts/scan``) and the Telegram bot;
both go through :mod:`app.services.receipt_ingest`. This is a third channel for a phone or
computer sync app (Syncthing, a network share, e-receipts saved from mail): it drops PDFs
and photos into ``RECEIPT_WATCH_DIR`` on the server instead, and :class:`ReceiptFolderWatcher`
reads them from there.

A file is taken only once it has been unchanged in size and mtime for
``RECEIPT_WATCH_SETTLE_SECONDS`` (so a sync still in progress is never read half-written),
is ingested through the same validation and duplicate check as every other channel, and is
then moved - never deleted - into ``processed/``, ``duplicates/`` or ``rejected/`` (with a
``<name>.reason.txt`` for the reason) inside the watched directory, atomically and on the
same filesystem.
"""

import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.services.receipt_ingest import (
    ReceiptTooLarge,
    UnsupportedReceiptType,
    ingest_receipt_file,
)

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# A dropped file has no declared content type (unlike an upload, which carries one), only
# its name, so we guess from its suffix - the inverse of
# receipt_ingest.SUFFIX_FOR_CONTENT_TYPE, which goes the other way for storage.
CONTENT_TYPE_FOR_SUFFIX: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Suffixes a sync tool uses for a file it has not finished writing yet.
_TEMP_SUFFIXES = (".part", ".tmp", "~")

PROCESSED_DIRNAME = "processed"
DUPLICATES_DIRNAME = "duplicates"
REJECTED_DIRNAME = "rejected"
_OUTPUT_DIRNAMES = (PROCESSED_DIRNAME, DUPLICATES_DIRNAME, REJECTED_DIRNAME)


def _is_ignored(name: str) -> bool:
    """Dotfiles (including Syncthing's ``.syncthing.*`` temp files) and temp suffixes."""
    if name.startswith("."):
        return True
    return name.endswith(_TEMP_SUFFIXES)


def _claim_destination(src: Path, target_dir: Path) -> Path:
    """Atomically claim a free name for ``src`` under ``target_dir``, then move it there.

    Two worker processes could archive a same-named file at the same moment; an
    ``exists()`` check followed by ``os.replace`` is two steps, not one, so the loser of
    that race would silently overwrite the winner's already-archived file.
    ``O_CREAT|O_EXCL`` is a single filesystem operation - only one process can create a
    given name - so the loser reliably sees ``FileExistsError`` and tries the next
    candidate (``-1``, ``-2``, ...) instead of clobbering it.
    """
    stem, suffix = src.stem, src.suffix
    name = src.name
    n = 0
    while True:
        candidate = target_dir / name
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1
            name = f"{stem}-{n}{suffix}"
            continue
        os.close(fd)
        break
    os.replace(src, candidate)
    return candidate


@dataclass
class _Seen:
    size: int
    mtime: float
    first_seen: float


class ReceiptFolderWatcher:
    """Scans a directory (not recursive) for settled files and ingests each one.

    State (which files have been noticed, and since when) lives on the instance, so the
    same watcher must be reused across polls - a fresh one forgets every file it had been
    waiting to settle.
    """

    def __init__(
        self,
        watch_dir: Path,
        *,
        settle_seconds: float,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.watch_dir = Path(watch_dir)
        self.settle_seconds = settle_seconds
        self._clock = clock
        self._seen: dict[str, _Seen] = {}
        self._warned_symlinks: set[str] = set()

    async def scan_once(self, session_factory: SessionFactory) -> int:
        """One pass over the folder. Returns how many files were read this pass."""
        try:
            entries = sorted(os.listdir(self.watch_dir))
        except FileNotFoundError:
            logger.warning(
                "Watched receipt folder does not exist",
                extra={"watch_dir": str(self.watch_dir)},
            )
            return 0
        except NotADirectoryError:
            logger.warning(
                "RECEIPT_WATCH_DIR is not a directory",
                extra={"watch_dir": str(self.watch_dir)},
            )
            return 0

        now = self._clock()
        taken = 0
        live_names: set[str] = set()

        for name in entries:
            if name in _OUTPUT_DIRNAMES or _is_ignored(name):
                continue
            path = self.watch_dir / name

            # F2: a symlink is never followed - is_symlink() uses lstat, so this never
            # touches whatever the link points at. A planted link is left alone (not
            # moved, not deleted) and logged once, not on every poll.
            if path.is_symlink():
                live_names.add(name)
                if name not in self._warned_symlinks:
                    logger.warning(
                        "Watched folder: ignoring a symlink (never read through a link)",
                        extra={"dropped_name": name},
                    )
                    self._warned_symlinks.add(name)
                continue

            try:
                if not path.is_file():
                    continue
                stat = path.stat()
            except OSError:
                continue  # removed or became unreadable between listdir and stat

            live_names.add(name)
            seen = self._seen.get(name)
            if seen is None or seen.size != stat.st_size or seen.mtime != stat.st_mtime:
                # First sighting of this exact size/mtime: start (or restart) the clock.
                self._seen[name] = _Seen(stat.st_size, stat.st_mtime, now)
                continue

            if now - seen.first_seen < self.settle_seconds:
                continue  # still settling

            try:
                processed = await self._ingest_one(session_factory, path, stat.st_size)
            except Exception as exc:
                # F1: isolate this file. A DB outage, a full disk, or any other fault
                # that is not one of the two *expected* rejections (handled inside
                # _ingest_one) must not abort the whole pass. The file stays exactly
                # where it is - its _seen entry is left untouched, already past
                # settling, so the next poll retries it immediately - and the loop
                # moves on to the next file.
                logger.warning(
                    "Watched folder: could not process a dropped file this pass",
                    extra={"dropped_name": name, "error": str(exc)},
                )
                continue

            if processed:
                taken += 1
            self._seen.pop(name, None)

        # Forget anything that is no longer there (we moved it, or it was removed) -
        # including a symlink we already warned about once, so a later regular file
        # reusing that name is not mistaken for the link and skipped silently.
        for stale in set(self._seen) - live_names:
            self._seen.pop(stale, None)
        self._warned_symlinks &= live_names

        return taken

    async def _ingest_one(
        self, session_factory: SessionFactory, path: Path, size: int
    ) -> bool:
        cap = settings.MAX_RECEIPT_UPLOAD_BYTES
        if size > cap:
            # F4: reject by the already-stat'd size, before reading the file at all.
            self._reject(
                path,
                f"Receipt is {size // 1_000_000} MB; the limit is {cap // 1_000_000} MB",
            )
            return True

        content_type = CONTENT_TYPE_FOR_SUFFIX.get(path.suffix.lower(), "")
        try:
            content = await anyio.Path(path).read_bytes()
        except OSError as exc:
            logger.warning(
                "Could not read a dropped receipt file",
                extra={"dropped_name": path.name, "error": str(exc)},
            )
            return False

        try:
            async with session_factory() as db:
                result = await ingest_receipt_file(
                    db, content=content, filename=path.name, content_type=content_type
                )
        except (UnsupportedReceiptType, ReceiptTooLarge) as exc:
            self._reject(path, str(exc))
            return True

        if result.duplicate:
            self._move(path, DUPLICATES_DIRNAME)
            logger.info(
                "Watched folder: duplicate receipt",
                extra={"receipt_id": str(result.receipt.id)},
            )
        else:
            self._move(path, PROCESSED_DIRNAME)
            logger.info(
                "Watched folder: receipt queued",
                extra={"receipt_id": str(result.receipt.id)},
            )
        return True

    def _reject(self, path: Path, reason: str) -> None:
        dest = self._move(path, REJECTED_DIRNAME)
        if dest is not None:
            dest.with_name(dest.name + ".reason.txt").write_text(reason + "\n")
        logger.info("Watched folder: rejected", extra={"dropped_name": path.name})

    def _move(self, path: Path, dirname: str) -> Path | None:
        target_dir = self.watch_dir / dirname
        try:
            target_dir.mkdir(exist_ok=True)
            dest = _claim_destination(path, target_dir)
        except OSError as exc:
            logger.warning(
                "Could not file a dropped receipt into its destination",
                extra={
                    "dropped_name": path.name,
                    "dest_dir": dirname,
                    "error": str(exc),
                },
            )
            return None
        return dest
