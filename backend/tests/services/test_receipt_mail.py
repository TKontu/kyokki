"""E-mail receipt drop-in (A2): e-receipts mailed to Kyokki are read like uploads.

Finnish chains (K-Ruoka, S-kanava, Lidl Plus) send e-receipts by mail, usually a PDF
attachment; the cook forwards them (or has them sent) to a dedicated mailbox.
``ReceiptMailPoller`` reads that mailbox over IMAP (faked here - never a real server) and
turns each allowed mail's attachment into a queued receipt through the same ``receipt_ingest``
path as every other channel, then moves the mail so it is never read twice.
"""

import base64
from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.receipt import Receipt
from app.services.receipt_mail import ReceiptMailPoller, build_mail_poller

PDF = b"%PDF-1.4 fake S-kaupat e-receipt"
JPEG = b"\xff\xd8\xff\xe0 fake jpeg bytes"
PNG = b"\x89PNG\r\n\x1a\n fake png bytes"
ALLOWED = frozenset({"cook@example.com", "@k-ruoka.example"})


# --------------------------------------------------------------------------------------
# A tiny in-process fake of the slice of imaplib this module calls - no network, ever.
# --------------------------------------------------------------------------------------


@dataclass
class _FakeMail:
    uid: int
    raw: bytes
    seen: bool = False
    deleted: bool = False


@dataclass
class FakeImapClient:
    mailboxes: dict[str, list[_FakeMail]]
    supports_move: bool = True
    fail_fetch_uids: set[int] = field(default_factory=set)
    selected: str | None = None
    logged_in: bool = False
    logged_out: bool = False
    created: list[str] = field(default_factory=list)

    def login(self, user, password):
        self.logged_in = True
        return ("OK", [b"logged in"])

    def select(self, mailbox):
        if mailbox not in self.mailboxes:
            return ("NO", [b"no such mailbox"])
        self.selected = mailbox
        return ("OK", [str(len(self.mailboxes[mailbox])).encode()])

    def create(self, mailbox):
        if mailbox in self.mailboxes:
            return ("NO", [b"already exists"])
        self.mailboxes[mailbox] = []
        self.created.append(mailbox)
        return ("OK", [b"created"])

    def capability(self):
        caps = b"IMAP4rev1 UIDPLUS" + (b" MOVE" if self.supports_move else b"")
        return ("OK", [caps])

    def _folder(self):
        return self.mailboxes[self.selected]

    def _find(self, uid: int) -> _FakeMail:
        for mail in self._folder():
            if mail.uid == uid:
                return mail
        raise KeyError(uid)

    def uid(self, command, *args):
        command = command.upper()
        if command == "SEARCH":
            unseen = [str(m.uid).encode() for m in self._folder() if not m.seen]
            return ("OK", [b" ".join(unseen)])
        if command == "FETCH":
            uid = int(args[0])
            if uid in self.fail_fetch_uids:
                raise OSError(f"simulated fetch failure for uid {uid}")
            mail = self._find(uid)
            return ("OK", [mail.raw])
        if command == "STORE":
            uid = int(args[0])
            flags = args[2]
            mail = self._find(uid)
            if "\\Seen" in flags:
                mail.seen = True
            if "\\Deleted" in flags:
                mail.deleted = True
            return ("OK", [b""])
        if command == "COPY":
            uid = int(args[0])
            dest = args[1]
            mail = self._find(uid)
            self.mailboxes.setdefault(dest, []).append(
                _FakeMail(uid=mail.uid, raw=mail.raw)
            )
            return ("OK", [b""])
        if command == "MOVE":
            if not self.supports_move:
                return ("NO", [b"MOVE not supported"])
            uid = int(args[0])
            dest = args[1]
            mail = self._find(uid)
            self._folder().remove(mail)
            self.mailboxes.setdefault(dest, []).append(mail)
            return ("OK", [b""])
        raise AssertionError(f"unhandled uid command: {command}")

    def expunge(self):
        self.mailboxes[self.selected] = [m for m in self._folder() if not m.deleted]
        return ("OK", [b""])

    def logout(self):
        self.logged_out = True
        return ("BYE", [b"logout"])


class _FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --------------------------------------------------------------------------------------
# Raw mail builders - hand-built MIME so the forwarded case (message/rfc822, 7bit) is
# exact and under our control, rather than hoping a high-level builder encodes it that way.
# --------------------------------------------------------------------------------------


def _b64_body(content: bytes) -> str:
    b64 = base64.b64encode(content).decode()
    return "\r\n".join(b64[i : i + 76] for i in range(0, len(b64), 76))


def _attachment_part(content_type: str, filename: str, content: bytes) -> bytes:
    return (
        f'Content-Type: {content_type}; name="{filename}"\r\n'
        f'Content-Disposition: attachment; filename="{filename}"\r\n'
        f"Content-Transfer-Encoding: base64\r\n\r\n{_b64_body(content)}\r\n"
    ).encode()


def _text_part(text: str = "See attached receipt.") -> bytes:
    return f"Content-Type: text/plain; charset=utf-8\r\n\r\n{text}\r\n".encode()


def _rfc822_part(inner_raw: bytes) -> bytes:
    return (
        b"Content-Type: message/rfc822\r\nContent-Transfer-Encoding: 7bit\r\n\r\n"
        + (inner_raw)
    )


def _mail(
    from_addr: str,
    *,
    subject: str = "Receipt",
    parts: list[bytes] | None = None,
    boundary: str = "BOUND1",
) -> bytes:
    header = (
        f"From: {from_addr}\r\n"
        f"To: receipts@kyokki.example\r\n"
        f"Subject: {subject}\r\n"
        f"MIME-Version: 1.0\r\n"
        f'Content-Type: multipart/mixed; boundary="{boundary}"\r\n\r\n'
    ).encode()
    body = b""
    for part in parts or [_text_part()]:
        body += f"--{boundary}\r\n".encode() + part + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return header + body


async def _count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Receipt))).scalar_one()


def _poller(
    client: FakeImapClient, *, clock: _FakeClock | None = None, allowed=ALLOWED
) -> ReceiptMailPoller:
    return ReceiptMailPoller(
        host="mail.example.com",
        port=993,
        user="receipts",
        password="secret",
        folder="INBOX",
        processed_folder="Kyokki/Processed",
        allowed_senders=allowed,
        connect=lambda host, port: client,
        clock=clock or _FakeClock(),
    )


def _client(mails: list[_FakeMail], **kwargs) -> FakeImapClient:
    return FakeImapClient(mailboxes={"INBOX": mails}, **kwargs)


class TestAllowedSenderWithAttachment:
    async def test_pdf_is_queued_and_mail_moves_to_processed(
        self, db_session: AsyncSession, session_factory
    ):
        raw = _mail(
            "cook@example.com",
            parts=[_text_part(), _attachment_part("application/pdf", "order.pdf", PDF)],
        )
        client = _client([_FakeMail(uid=1, raw=raw)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 1
        assert await _count(db_session) == 1
        assert client.mailboxes["INBOX"] == []
        assert len(client.mailboxes["Kyokki/Processed"]) == 1
        assert client.logged_out is True

    @pytest.mark.parametrize(
        "content_type,filename,content",
        [
            ("image/jpeg", "order.jpg", JPEG),
            ("image/png", "order.png", PNG),
        ],
    )
    async def test_image_attachments_are_queued(
        self,
        db_session: AsyncSession,
        session_factory,
        content_type,
        filename,
        content,
    ):
        raw = _mail(
            "cook@example.com",
            parts=[_attachment_part(content_type, filename, content)],
        )
        client = _client([_FakeMail(uid=1, raw=raw)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 1
        assert await _count(db_session) == 1
        assert len(client.mailboxes["Kyokki/Processed"]) == 1


class TestRefusedSender:
    async def test_sender_not_allowed_is_only_marked_seen(
        self, db_session: AsyncSession, session_factory
    ):
        raw = _mail(
            "stranger@evil.example",
            parts=[_attachment_part("application/pdf", "order.pdf", PDF)],
        )
        client = _client([_FakeMail(uid=1, raw=raw)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 0
        assert await _count(db_session) == 0
        # left in place, not moved, but flagged seen so it is never read again
        assert len(client.mailboxes["INBOX"]) == 1
        assert client.mailboxes["INBOX"][0].seen is True
        assert "Kyokki/Processed" not in client.mailboxes or not client.mailboxes.get(
            "Kyokki/Processed"
        )


class TestNoUsableAttachment:
    async def test_mail_with_no_attachment_is_only_marked_seen(
        self, db_session: AsyncSession, session_factory
    ):
        raw = _mail("cook@example.com", parts=[_text_part("Just a note, no receipt.")])
        client = _client([_FakeMail(uid=1, raw=raw)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 0
        assert await _count(db_session) == 0
        assert client.mailboxes["INBOX"][0].seen is True

    async def test_unsupported_attachment_type_is_treated_as_no_attachment(
        self, db_session: AsyncSession, session_factory
    ):
        raw = _mail(
            "cook@example.com",
            parts=[_attachment_part("text/plain", "note.txt", b"not a receipt")],
        )
        client = _client([_FakeMail(uid=1, raw=raw)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 0
        assert await _count(db_session) == 0
        assert client.mailboxes["INBOX"][0].seen is True

    async def test_oversized_attachment_is_treated_as_no_attachment(
        self,
        db_session: AsyncSession,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(settings, "MAX_RECEIPT_UPLOAD_BYTES", 8)
        raw = _mail(
            "cook@example.com",
            parts=[_attachment_part("application/pdf", "huge.pdf", PDF)],
        )
        client = _client([_FakeMail(uid=1, raw=raw)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 0
        assert await _count(db_session) == 0
        assert client.mailboxes["INBOX"][0].seen is True
        assert not client.mailboxes.get("Kyokki/Processed")


class TestForwardedMail:
    async def test_attachment_inside_a_forwarded_mail_is_queued(
        self, db_session: AsyncSession, session_factory
    ):
        inner = _mail(
            "noreply@k-ruoka.example",
            subject="Your e-receipt",
            parts=[_attachment_part("application/pdf", "kuitti.pdf", PDF)],
            boundary="INNER",
        )
        outer = _mail(
            "cook@example.com",
            subject="Fwd: Your e-receipt",
            parts=[_text_part("Forwarded for you."), _rfc822_part(inner)],
            boundary="OUTER",
        )
        client = _client([_FakeMail(uid=1, raw=outer)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 1
        assert await _count(db_session) == 1
        assert len(client.mailboxes["Kyokki/Processed"]) == 1


class TestDuplicate:
    async def test_a_duplicate_attachment_still_moves_its_mail(
        self, db_session: AsyncSession, session_factory
    ):
        first = _mail(
            "cook@example.com",
            parts=[_attachment_part("application/pdf", "order.pdf", PDF)],
        )
        second = _mail(
            "cook@example.com",
            subject="Receipt (again)",
            parts=[_attachment_part("application/pdf", "order-copy.pdf", PDF)],
        )
        client = _client([_FakeMail(uid=1, raw=first), _FakeMail(uid=2, raw=second)])
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        # Both mails are handled (their attachment ingests without error) and both move;
        # only one Receipt row exists, since the second attachment is the same bytes.
        assert queued == 2
        assert await _count(db_session) == 1
        assert client.mailboxes["INBOX"] == []
        assert len(client.mailboxes["Kyokki/Processed"]) == 2


class TestMoveFallback:
    async def test_copy_delete_expunge_when_move_is_unsupported(
        self, db_session: AsyncSession, session_factory
    ):
        raw = _mail(
            "cook@example.com",
            parts=[_attachment_part("application/pdf", "order.pdf", PDF)],
        )
        client = _client([_FakeMail(uid=1, raw=raw)], supports_move=False)
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 1
        assert await _count(db_session) == 1
        assert client.mailboxes["INBOX"] == []  # expunged after being flagged \Deleted
        assert len(client.mailboxes["Kyokki/Processed"]) == 1


class TestIsolatedFailures:
    async def test_one_bad_mail_does_not_stop_the_rest(
        self, db_session: AsyncSession, session_factory
    ):
        bad = _mail(
            "cook@example.com",
            parts=[_attachment_part("application/pdf", "bad.pdf", PDF)],
        )
        good = _mail(
            "cook@example.com",
            subject="Receipt 2",
            parts=[_attachment_part("application/pdf", "good.pdf", PDF + b"-distinct")],
        )
        client = _client(
            [_FakeMail(uid=1, raw=bad), _FakeMail(uid=2, raw=good)],
            fail_fetch_uids={1},
        )
        poller = _poller(client)

        queued = await poller.poll_once(session_factory)

        assert queued == 1
        assert await _count(db_session) == 1
        # the bad mail's fetch failed before it could be flagged seen or moved
        assert len(client.mailboxes["INBOX"]) == 1
        assert client.mailboxes["INBOX"][0].uid == 1
        assert len(client.mailboxes["Kyokki/Processed"]) == 1


class TestConnectionFailure:
    async def test_a_connection_error_is_logged_and_retried_with_backoff(
        self, session_factory
    ):
        calls = {"n": 0}

        def flaky_connect(host, port):
            calls["n"] += 1
            raise OSError("connection refused")

        clock = _FakeClock()
        poller = ReceiptMailPoller(
            host="mail.example.com",
            port=993,
            user="receipts",
            password="secret",
            folder="INBOX",
            processed_folder="Kyokki/Processed",
            allowed_senders=ALLOWED,
            connect=flaky_connect,
            clock=clock,
        )

        queued = await poller.poll_once(session_factory)
        assert queued == 0
        assert calls["n"] == 1  # one connection attempt, logged, not raised

        # Immediately polling again must not hammer the server: still backed off.
        queued = await poller.poll_once(session_factory)
        assert queued == 0
        assert calls["n"] == 1

        # Once the backoff has elapsed, the next poll tries again.
        clock.advance(3600)
        queued = await poller.poll_once(session_factory)
        assert queued == 0
        assert calls["n"] == 2

    async def test_recovery_resets_the_backoff(
        self, db_session: AsyncSession, session_factory
    ):
        calls = {"n": 0}
        raw = _mail(
            "cook@example.com",
            parts=[_attachment_part("application/pdf", "order.pdf", PDF)],
        )
        client = _client([_FakeMail(uid=1, raw=raw)])

        def connect(host, port):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("connection refused")
            return client

        clock = _FakeClock()
        poller = ReceiptMailPoller(
            host="mail.example.com",
            port=993,
            user="receipts",
            password="secret",
            folder="INBOX",
            processed_folder="Kyokki/Processed",
            allowed_senders=ALLOWED,
            connect=connect,
            clock=clock,
        )

        assert await poller.poll_once(session_factory) == 0  # fails, backs off
        clock.advance(3600)
        assert await poller.poll_once(session_factory) == 1  # recovers
        assert await _count(db_session) == 1


class TestBuildMailPoller:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch, caplog):
        monkeypatch.setattr(settings, "RECEIPT_MAIL_HOST", "")
        with caplog.at_level("INFO", logger="app.services.receipt_mail"):
            poller = build_mail_poller(settings)

        assert poller is None
        assert any("disabled" in r.message for r in caplog.records)

    def test_enabled_with_empty_allowlist_refuses_to_scan(
        self, monkeypatch: pytest.MonkeyPatch, caplog
    ):
        monkeypatch.setattr(settings, "RECEIPT_MAIL_HOST", "mail.example.com")
        monkeypatch.setattr(settings, "RECEIPT_MAIL_ALLOWED_SENDERS", [])
        with caplog.at_level("ERROR", logger="app.services.receipt_mail"):
            poller = build_mail_poller(settings)

        assert poller is None
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(errors) == 1
        assert "ALLOWED_SENDERS" in errors[0].message

    def test_enabled_with_an_allowlist_builds_a_poller(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "RECEIPT_MAIL_HOST", "mail.example.com")
        monkeypatch.setattr(
            settings, "RECEIPT_MAIL_ALLOWED_SENDERS", ["cook@example.com"]
        )

        poller = build_mail_poller(settings)

        assert poller is not None
        assert poller.host == "mail.example.com"
        assert poller.allowed_senders == frozenset({"cook@example.com"})
