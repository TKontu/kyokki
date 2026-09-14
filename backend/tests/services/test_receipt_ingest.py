"""Shared receipt ingest for the upload API and the Telegram bot (MVP-T1)."""

import hashlib
import shutil
from unittest.mock import patch

import anyio
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.services.receipt_ingest import (
    UnsupportedReceiptType,
    ingest_receipt_file,
)

PDF = b"%PDF-1.4 fake S-kaupat order receipt"


@pytest.fixture(autouse=True)
async def _clean_receipt_files():
    yield
    receipts_dir = anyio.Path("data/receipts")
    if await receipts_dir.exists():
        shutil.rmtree(str(receipts_dir))


async def _count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Receipt))).scalar_one()


async def test_new_file_creates_a_receipt_with_its_hash(db_session: AsyncSession):
    result = await ingest_receipt_file(
        db_session, content=PDF, filename="order.pdf", content_type="application/pdf"
    )

    assert result.duplicate is False
    assert result.receipt.content_sha256 == hashlib.sha256(PDF).hexdigest()
    assert result.receipt.processing_status == "uploaded"
    assert await anyio.Path(result.receipt.image_path).read_bytes() == PDF


async def test_same_bytes_under_another_name_is_a_duplicate(db_session: AsyncSession):
    first = await ingest_receipt_file(
        db_session, content=PDF, filename="order.pdf", content_type="application/pdf"
    )
    second = await ingest_receipt_file(
        db_session,
        content=PDF,
        filename="kuitti (1).pdf",
        content_type="application/pdf",
    )

    assert second.duplicate is True
    assert second.receipt.id == first.receipt.id
    assert await _count(db_session) == 1


@pytest.mark.parametrize("content_type", ["text/plain", "application/zip", ""])
async def test_unsupported_content_type_is_refused(
    db_session: AsyncSession, content_type
):
    with pytest.raises(UnsupportedReceiptType):
        await ingest_receipt_file(
            db_session, content=b"x", filename="x.txt", content_type=content_type
        )
    assert await _count(db_session) == 0


async def test_unique_violation_race_returns_the_existing_receipt(
    db_session: AsyncSession,
):
    from app.crud import receipt as crud_receipt

    first = await ingest_receipt_file(
        db_session, content=PDF, filename="order.pdf", content_type="application/pdf"
    )
    first_id = first.receipt.id
    real_lookup = crud_receipt.get_receipt_by_sha256
    calls = 0

    async def lookup_misses_once(db, sha256):
        # The concurrent request's lookup ran before the first upload committed
        nonlocal calls
        calls += 1
        return None if calls == 1 else await real_lookup(db, sha256)

    with (
        patch(
            "app.services.receipt_ingest.crud_receipt.get_receipt_by_sha256",
            side_effect=lookup_misses_once,
        ),
        patch(
            "app.services.receipt_ingest.crud_receipt.create_receipt",
            side_effect=IntegrityError("insert", {}, Exception("duplicate key")),
        ),
    ):
        second = await ingest_receipt_file(
            db_session,
            content=PDF,
            filename="order.pdf",
            content_type="application/pdf",
        )

    assert second.duplicate is True
    assert second.receipt.id == first_id
