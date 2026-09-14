"""API endpoints for Receipt upload and management."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import handle_integrity_errors
from app.crud import receipt as crud_receipt
from app.db.session import get_db
from app.schemas.receipt import (
    ReceiptConfirmRequest,
    ReceiptConfirmResponse,
    ReceiptResponse,
    ReceiptStatus,
)
from app.services import receipt_confirm, receipt_queue
from app.services.receipt_ingest import UnsupportedReceiptType, ingest_receipt_file

router = APIRouter()


@router.post(
    "/scan", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED
)
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
        HTTPException 409: If the same file was already uploaded (detail has receipt_id).
    """
    try:
        result = await ingest_receipt_file(
            db,
            content=await file.read(),
            filename=file.filename or "receipt",
            content_type=file.content_type or "",
            store_chain=store_chain,
            purchase_date=purchase_date,
        )
    except UnsupportedReceiptType as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if result.duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Receipt already uploaded",
                "receipt_id": str(result.receipt.id),
            },
        )

    return result.receipt


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
    # A receipt stuck in processing (worker down) reads as failed so it can be retried
    await receipt_queue.fail_stale(db)
    receipt = await crud_receipt.get_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' not found",
        )
    return receipt


@router.get("", response_model=list[ReceiptResponse])
async def list_receipts(
    status: ReceiptStatus | None = None,
    store: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ReceiptResponse]:
    """Get all receipts with optional filtering.

    Args:
        status: Optional filter by processing status; unknown values are rejected (422).
        store: Optional filter by store_chain.
        db: Database session.

    Returns:
        List of receipts sorted by created_at (most recent first).
    """
    await receipt_queue.fail_stale(db)
    receipts = await crud_receipt.get_receipts(
        db,
        status=status,
        store_chain=store,
    )
    return receipts


@router.post(
    "/{receipt_id}/process",
    response_model=ReceiptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReceiptResponse:
    """Queue a failed (or pre-queue ``uploaded``) receipt to be read again.

    Uploads are queued automatically; the worker service (``python -m app.worker``) reads
    queued receipts one at a time. This endpoint never runs the pipeline itself.

    Raises:
        HTTPException 404: Receipt not found.
        HTTPException 409: Receipt is queued, processing, or was already read.
    """
    await receipt_queue.fail_stale(db)
    receipt = await crud_receipt.get_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' not found",
        )
    if receipt.processing_status in (ReceiptStatus.QUEUED, ReceiptStatus.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt is already queued or processing",
        )
    if receipt.processing_status in (ReceiptStatus.COMPLETED, ReceiptStatus.CONFIRMED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt was already read",
        )

    await receipt_queue.enqueue(db, receipt)
    return ReceiptResponse.model_validate(receipt)


@router.post("/{receipt_id}/confirm", response_model=ReceiptConfirmResponse)
async def confirm_receipt(
    receipt_id: UUID,
    confirm_request: ReceiptConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> ReceiptConfirmResponse:
    """Confirm reviewed receipt items: create inventory, generic products and store aliases.

    Items not sent are skipped. The whole confirm is one transaction.

    Raises:
        HTTPException 404: Receipt not found.
        HTTPException 409: Receipt already confirmed or not read yet.
        HTTPException 400: An item names an unknown product, line or category.
    """
    try:
        async with handle_integrity_errors():
            result = await receipt_confirm.confirm_receipt(
                db, receipt_id, confirm_request.items
            )
    except receipt_confirm.ReceiptNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except receipt_confirm.ReceiptNotConfirmable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except receipt_confirm.InvalidConfirmItem as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ReceiptConfirmResponse(
        success=True,
        items_created=result.items_created,
        products_created=result.products_created,
        aliases_learned=result.aliases_learned,
        error=None,
    )
