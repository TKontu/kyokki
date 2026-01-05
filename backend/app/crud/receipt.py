"""CRUD operations for Receipt model."""
from datetime import date
from pathlib import Path
from uuid import UUID
import uuid
import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt
from app.schemas.receipt import ReceiptUpdate


async def get_receipts(
    db: AsyncSession,
    *,
    status: str | None = None,
    store_chain: str | None = None,
) -> list[Receipt]:
    """Get all receipts with optional filtering.

    Args:
        db: Database session.
        status: Optional filter by processing_status.
        store_chain: Optional filter by store_chain.

    Returns:
        List of receipts sorted by created_at descending (most recent first).
    """
    query = select(Receipt)

    # Apply filters
    if status:
        query = query.where(Receipt.processing_status == status)
    if store_chain:
        query = query.where(Receipt.store_chain == store_chain)

    # Sort by most recent first
    query = query.order_by(Receipt.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_receipt(db: AsyncSession, receipt_id: UUID) -> Receipt | None:
    """Get a receipt by ID.

    Args:
        db: Database session.
        receipt_id: Receipt UUID.

    Returns:
        Receipt if found, None otherwise.
    """
    result = await db.execute(
        select(Receipt).where(Receipt.id == receipt_id)
    )
    return result.scalar_one_or_none()


async def create_receipt(
    db: AsyncSession,
    *,
    file_content: bytes,
    filename: str,
    store_chain: str | None = None,
    purchase_date: date | None = None,
    batch_id: UUID | None = None,
) -> Receipt:
    """Create a new receipt with file storage.

    Args:
        db: Database session.
        file_content: The uploaded file bytes.
        filename: Original filename (used for extension).
        store_chain: Optional store chain name.
        purchase_date: Optional purchase date.
        batch_id: Optional batch ID for multi-receipt processing.

    Returns:
        Created receipt.
    """
    # Generate unique filename
    receipt_id = uuid.uuid4()
    file_extension = Path(filename).suffix
    stored_filename = f"{receipt_id}{file_extension}"

    # Ensure receipts directory exists
    receipts_dir = Path("data/receipts")
    receipts_dir.mkdir(parents=True, exist_ok=True)

    # Save file to disk
    file_path = receipts_dir / stored_filename
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_content)

    # Create database record
    db_receipt = Receipt(
        id=receipt_id,
        store_chain=store_chain,
        purchase_date=purchase_date,
        image_path=str(file_path),
        processing_status="uploaded",
        batch_id=batch_id,
        items_extracted=0,
        items_matched=0,
    )

    db.add(db_receipt)
    await db.commit()
    await db.refresh(db_receipt)
    return db_receipt


async def update_receipt(
    db: AsyncSession,
    receipt_id: UUID,
    receipt_update: ReceiptUpdate,
) -> Receipt | None:
    """Update a receipt.

    Args:
        db: Database session.
        receipt_id: Receipt UUID.
        receipt_update: Receipt update data.

    Returns:
        Updated receipt if found, None otherwise.
    """
    db_receipt = await get_receipt(db, receipt_id)
    if not db_receipt:
        return None

    update_data = receipt_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_receipt, field, value)

    await db.commit()
    await db.refresh(db_receipt)
    return db_receipt


async def delete_receipt(db: AsyncSession, receipt_id: UUID) -> bool:
    """Delete a receipt.

    Args:
        db: Database session.
        receipt_id: Receipt UUID.

    Returns:
        True if deleted, False if not found.
    """
    db_receipt = await get_receipt(db, receipt_id)
    if not db_receipt:
        return False

    # Delete file from disk
    file_path = Path(db_receipt.image_path)
    if file_path.exists():
        file_path.unlink()

    # Delete database record
    await db.delete(db_receipt)
    await db.commit()
    return True
