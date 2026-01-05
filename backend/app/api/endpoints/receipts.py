"""API endpoints for Receipt upload and management."""
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.crud import receipt as crud_receipt
from app.schemas.receipt import ReceiptResponse


router = APIRouter()

# Allowed file types for receipt upload
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/pdf",
}


@router.post("/scan", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    file: UploadFile = File(...),
    store_chain: str | None = Form(None),
    purchase_date: date | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> ReceiptResponse:
    """Upload a receipt image or PDF for processing.

    Args:
        file: The receipt image or PDF file.
        store_chain: Optional store chain name (e.g., "S-Market", "K-Citymarket").
        purchase_date: Optional purchase date.
        db: Database session.

    Returns:
        Created receipt with metadata.

    Raises:
        HTTPException 400: If file type is not supported.
    """
    # Validate file type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    # Read file content
    file_content = await file.read()

    # Create receipt with file storage
    receipt = await crud_receipt.create_receipt(
        db,
        file_content=file_content,
        filename=file.filename or "receipt",
        store_chain=store_chain,
        purchase_date=purchase_date,
    )

    return receipt


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReceiptResponse:
    """Get a specific receipt by ID.

    Args:
        receipt_id: Receipt UUID.
        db: Database session.

    Returns:
        Receipt with metadata and processing status.

    Raises:
        HTTPException 404: If receipt not found.
    """
    receipt = await crud_receipt.get_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' not found",
        )
    return receipt


@router.get("", response_model=list[ReceiptResponse])
async def list_receipts(
    status: str | None = None,
    store: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ReceiptResponse]:
    """Get all receipts with optional filtering.

    Args:
        status: Optional filter by processing_status (e.g., "uploaded", "processing", "completed").
        store: Optional filter by store_chain.
        db: Database session.

    Returns:
        List of receipts sorted by created_at (most recent first).
    """
    receipts = await crud_receipt.get_receipts(
        db,
        status=status,
        store_chain=store,
    )
    return receipts
