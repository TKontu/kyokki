"""Receipt ingest shared by every upload channel (iPad upload API, Telegram bot).

One place decides which files are accepted and whether a file was already received, so the
same PDF shared twice never becomes two receipts (and, after R2, double inventory).
"""

import hashlib
from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import receipt as crud_receipt
from app.models.receipt import Receipt

logger = get_logger(__name__)

ALLOWED_CONTENT_TYPES = frozenset(
    {"application/pdf", "image/jpeg", "image/jpg", "image/png", "image/webp"}
)


class UnsupportedReceiptType(ValueError):
    """The file is not a PDF or a supported image."""


@dataclass(frozen=True)
class IngestResult:
    receipt: Receipt
    duplicate: bool


async def ingest_receipt_file(
    db: AsyncSession,
    *,
    content: bytes,
    filename: str,
    content_type: str,
    store_chain: str | None = None,
    purchase_date: date | None = None,
) -> IngestResult:
    """Store a new receipt file, or return the receipt that already has these exact bytes.

    Raises:
        UnsupportedReceiptType: ``content_type`` is not a PDF or supported image.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedReceiptType(
            f"Unsupported file type: {content_type or 'unknown'}. "
            f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    sha256 = hashlib.sha256(content).hexdigest()
    existing = await crud_receipt.get_receipt_by_sha256(db, sha256)
    if existing is not None:
        logger.info("Duplicate receipt file", extra={"receipt_id": str(existing.id)})
        return IngestResult(receipt=existing, duplicate=True)

    try:
        receipt = await crud_receipt.create_receipt(
            db,
            file_content=content,
            filename=filename,
            store_chain=store_chain,
            purchase_date=purchase_date,
            content_sha256=sha256,
        )
    except IntegrityError:
        # A concurrent upload of the same file committed first (unique index on the hash)
        await db.rollback()
        existing = await crud_receipt.get_receipt_by_sha256(db, sha256)
        if existing is None:
            raise
        return IngestResult(receipt=existing, duplicate=True)

    return IngestResult(receipt=receipt, duplicate=False)
