"""E-mail receipt drop-in: e-receipts mailed to Kyokki are read like uploads.

Receipts arrive today by iPad upload (``POST /api/receipts/scan``), the Telegram bot and the
watched folder (:mod:`app.services.receipt_folder`); all go through
:mod:`app.services.receipt_ingest`. This is a fourth channel: Finnish chains (K-Ruoka,
S-kanava, Lidl Plus) send e-receipts by mail, usually as a PDF attachment, and the cook
forwards them - or has them sent - to a dedicated mailbox. ``ReceiptMailPoller`` polls that
mailbox over IMAP and ingests each PDF/JPEG/PNG attachment it finds, including one inside a
forwarded ``message/rfc822`` part, through the same validation and duplicate check as every
other channel.

Design notes:
- IMAP over TLS with the standard library ``imaplib``; every blocking call runs off the event
  loop through ``asyncio.to_thread`` so the worker's queue claim is never blocked on network
  I/O. Calls are made one at a time (never concurrently) against the same connection, so
  ``imaplib``'s lack of thread-safety is never actually exercised.
- Nothing is cached across polls: unlike the watched folder (which has no server-side "already
  read" marker and must remember file identity itself), IMAP's own ``\\Seen`` flag and the move
  to ``PROCESSED_FOLDER`` *are* the record of what has already been read.
- A connection failure (the mailbox is down, DNS fails, auth is rejected) backs off
  exponentially (30s, 60s, ... capped at 1h) instead of hammering the server every poll; a
  per-mail failure (one malformed message) is isolated and never aborts the rest of the pass,
  matching the watched folder's isolation.
"""

import asyncio
import contextlib
import imaplib
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from email import message_from_bytes
from email.message import Message
from email.utils import parseaddr
from time import monotonic
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.receipt_ingest import (
    ReceiptTooLarge,
    UnsupportedReceiptType,
    ingest_receipt_file,
)

logger = get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# The three attachment kinds Finnish e-receipts arrive as. HTML-only e-receipts (no
# attachment) are out of scope - they fall into the "no attachment" bucket below.
ATTACHMENT_CONTENT_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png"})

_BACKOFF_INITIAL_SECONDS = 30.0
_BACKOFF_MAX_SECONDS = 3600.0


class ReceiptMailConnectionError(RuntimeError):
    """The mailbox could not be reached, logged in to, or searched this poll."""


class ImapClient(Protocol):
    """The slice of ``imaplib.IMAP4``/``IMAP4_SSL`` this module calls.

    A test fakes this interface in-process (no network); production gets a real
    ``imaplib.IMAP4_SSL`` from :func:`_default_connect`.
    """

    def login(self, user: str, password: str) -> tuple: ...
    def select(self, mailbox: str) -> tuple: ...
    def create(self, mailbox: str) -> tuple: ...
    def capability(self) -> tuple: ...
    def uid(self, command: str, *args: str) -> tuple: ...
    def expunge(self) -> tuple: ...
    def logout(self) -> tuple: ...


ConnectFn = Callable[[str, int], ImapClient]


def _default_connect(host: str, port: int) -> ImapClient:
    return imaplib.IMAP4_SSL(host, port)


@dataclass(frozen=True)
class _Attachment:
    filename: str
    content_type: str
    content: bytes


def _domain_of(from_header: str) -> str:
    _, addr = parseaddr(from_header)
    addr = addr.strip().lower()
    return addr.rsplit("@", 1)[1] if "@" in addr else ""


def _sender_allowed(from_header: str, allowed: frozenset[str]) -> bool:
    _, addr = parseaddr(from_header)
    addr = addr.strip().lower()
    if not addr or "@" not in addr:
        return False
    domain = addr.rsplit("@", 1)[1]
    return addr in allowed or f"@{domain}" in allowed


def _iter_attachments(msg: Message) -> list[_Attachment]:
    """Every PDF/JPEG/PNG part, descending into a forwarded ``message/rfc822`` part.

    No special-casing is needed for the forwarded case: Python's parser gives a
    ``message/rfc822`` part (sent, as mail requires, with a 7bit/8bit transfer encoding) a
    payload of ``[<the forwarded Message>]``, which makes ``is_multipart()`` true for it -
    so ``Message.walk()`` already recurses into the forwarded message and its own parts.
    """
    found: list[_Attachment] = []
    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type not in ATTACHMENT_CONTENT_TYPES:
            continue
        content = part.get_payload(decode=True)
        if not content:
            continue
        filename = part.get_filename() or "attachment"
        found.append(
            _Attachment(filename=filename, content_type=content_type, content=content)
        )
    return found


class ReceiptMailPoller:
    """Polls one IMAP mailbox and ingests each allowed mail's attachments."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        folder: str,
        processed_folder: str,
        allowed_senders: frozenset[str],
        connect: ConnectFn = _default_connect,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.folder = folder
        self.processed_folder = processed_folder
        self.allowed_senders = allowed_senders
        self._connect = connect
        self._clock = clock
        self._backoff_seconds = 0.0
        self._retry_at = float("-inf")

    async def poll_once(self, session_factory: SessionFactory) -> int:
        """One pass over unseen mail. Returns how many receipts were queued this pass."""
        now = self._clock()
        if now < self._retry_at:
            return 0

        try:
            client = await asyncio.to_thread(self._connect, self.host, self.port)
            await asyncio.to_thread(client.login, self.user, self.password)
            await asyncio.to_thread(self._ensure_processed_folder, client)
            typ, _ = await asyncio.to_thread(client.select, self.folder)
            if typ != "OK":
                raise ReceiptMailConnectionError(
                    f"could not select the mail folder (got {typ})"
                )
            supports_move = await asyncio.to_thread(self._supports_move, client)
            typ, data = await asyncio.to_thread(client.uid, "SEARCH", None, "UNSEEN")
            if typ != "OK":
                raise ReceiptMailConnectionError(f"IMAP search failed (got {typ})")
        except Exception as exc:
            self._on_connection_failure(exc)
            return 0

        uids = data[0].split() if data and data[0] else []
        queued = 0
        for raw_uid in uids:
            uid = raw_uid.decode() if isinstance(raw_uid, bytes) else str(raw_uid)
            try:
                queued += await self._handle_one(
                    session_factory, client, uid, supports_move
                )
            except Exception as exc:
                # One malformed or unreadable mail must never stop the rest of the pass.
                logger.warning(
                    "E-mail receipt: could not process one mail this pass",
                    extra={"error": str(exc)},
                )

        with contextlib.suppress(Exception):
            await asyncio.to_thread(client.logout)

        self._backoff_seconds = 0.0
        self._retry_at = float("-inf")
        return queued

    def _on_connection_failure(self, exc: Exception) -> None:
        self._backoff_seconds = min(
            max(self._backoff_seconds * 2, _BACKOFF_INITIAL_SECONDS),
            _BACKOFF_MAX_SECONDS,
        )
        self._retry_at = self._clock() + self._backoff_seconds
        logger.warning(
            "E-mail receipt mailbox unreachable; retrying with backoff",
            extra={"error": str(exc), "backoff_seconds": self._backoff_seconds},
        )

    async def _handle_one(
        self,
        session_factory: SessionFactory,
        client: ImapClient,
        uid: str,
        supports_move: bool,
    ) -> int:
        typ, data = await asyncio.to_thread(client.uid, "FETCH", uid, "(RFC822)")
        if typ != "OK" or not data or not data[0]:
            raise ReceiptMailConnectionError(f"fetch failed for one mail (got {typ})")
        msg = message_from_bytes(data[0])
        from_header = msg.get("From", "")

        if not _sender_allowed(from_header, self.allowed_senders):
            logger.info(
                "E-mail receipt: sender not allowed",
                extra={
                    "sender_domain": _domain_of(from_header),
                    "reason": "sender not allowed",
                },
            )
            await asyncio.to_thread(self._mark_seen, client, uid)
            return 0

        queued = 0
        for attachment in _iter_attachments(msg):
            try:
                async with session_factory() as db:
                    await ingest_receipt_file(
                        db,
                        content=attachment.content,
                        filename=attachment.filename,
                        content_type=attachment.content_type,
                    )
            except (UnsupportedReceiptType, ReceiptTooLarge) as exc:
                logger.info(
                    "E-mail receipt: attachment skipped",
                    extra={"reason": str(exc)},
                )
                continue
            queued += 1

        if queued == 0:
            logger.info(
                "E-mail receipt: no attachment",
                extra={
                    "sender_domain": _domain_of(from_header),
                    "reason": "no attachment",
                },
            )
            await asyncio.to_thread(self._mark_seen, client, uid)
            return 0

        await asyncio.to_thread(self._move, client, uid, supports_move)
        logger.info("E-mail receipt: queued", extra={"attachments_queued": queued})
        return queued

    def _ensure_processed_folder(self, client: ImapClient) -> None:
        # Already exists, or the server rejected it for another reason - either way,
        # SELECT below is the real check for whether the mailbox is usable.
        with contextlib.suppress(Exception):
            client.create(self.processed_folder)

    def _supports_move(self, client: ImapClient) -> bool:
        try:
            typ, data = client.capability()
        except Exception:
            return False
        if typ != "OK" or not data or not isinstance(data[0], bytes):
            return False
        return b"MOVE" in data[0].upper().split()

    def _mark_seen(self, client: ImapClient, uid: str) -> None:
        client.uid("STORE", uid, "+FLAGS", "(\\Seen)")

    def _move(self, client: ImapClient, uid: str, supports_move: bool) -> None:
        if supports_move:
            typ, _ = client.uid("MOVE", uid, self.processed_folder)
            if typ == "OK":
                return
        # MOVE unsupported, or attempted and refused: copy, flag deleted, expunge.
        client.uid("COPY", uid, self.processed_folder)
        client.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        client.expunge()


def build_mail_poller(cfg: Settings) -> ReceiptMailPoller | None:
    """Build the poller from settings, logging the enable/disable decision once.

    Mirrors ``app.services.receipt_folder``'s "empty setting disables, logged at startup"
    pattern, plus one extra ruling: an enabled adapter with no allowlist refuses to scan -
    logged as one ERROR - rather than accept mail from anyone who knows the mailbox address.
    """
    if not cfg.RECEIPT_MAIL_HOST:
        logger.info("E-mail receipts disabled (RECEIPT_MAIL_HOST is empty)")
        return None

    allowed = frozenset(
        s.strip().lower() for s in cfg.RECEIPT_MAIL_ALLOWED_SENDERS if s.strip()
    )
    if not allowed:
        logger.error(
            "Refusing to start the e-mail receipt scan: RECEIPT_MAIL_ALLOWED_SENDERS is "
            "empty. Anyone who knows the mailbox address must not be able to inject "
            "receipts; set it to the allowed addresses or @domains to enable the scan."
        )
        return None

    password = (
        cfg.RECEIPT_MAIL_PASSWORD.get_secret_value()
        if cfg.RECEIPT_MAIL_PASSWORD is not None
        else ""
    )
    return ReceiptMailPoller(
        host=cfg.RECEIPT_MAIL_HOST,
        port=cfg.RECEIPT_MAIL_PORT,
        user=cfg.RECEIPT_MAIL_USER,
        password=password,
        folder=cfg.RECEIPT_MAIL_FOLDER,
        processed_folder=cfg.RECEIPT_MAIL_PROCESSED_FOLDER,
        allowed_senders=allowed,
    )
