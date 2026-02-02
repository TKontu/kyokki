"""API endpoints for Receipt upload and management."""
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import receipt as crud_receipt
from app.db.session import get_db
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.schemas.receipt import (
    ReceiptConfirmRequest,
    ReceiptConfirmResponse,
    ReceiptProcessingResponse,
    ReceiptResponse,
)
from app.services.broadcast_helpers import broadcast_receipt_status
from app.services.llm_extractor import extract_products_from_receipt
from app.services.ocr_service import extract_text_from_receipt
from app.services.receipt_processing import ReceiptProcessingService


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


@router.post("/{receipt_id}/process", response_model=ReceiptProcessingResponse)
async def process_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReceiptProcessingResponse:
    """Process a receipt through OCR → LLM extraction → product matching pipeline.

    This endpoint triggers the full receipt processing workflow:
    1. Extract text via OCR (pdfplumber for PDFs, MinerU for images)
    2. Extract products via LLM (vLLM with structured output)
    3. Match extracted products to canonical products using fuzzy matching
    4. Update receipt record with results

    Args:
        receipt_id: Receipt UUID to process.
        db: Database session.

    Returns:
        Processing result with extraction and matching statistics.

    Raises:
        HTTPException 404: If receipt not found.
    """
    # Get receipt
    receipt = await crud_receipt.get_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' not found",
        )

    # Process receipt
    processing_service = ReceiptProcessingService(db)
    result = await processing_service.process_receipt(receipt)

    return ReceiptProcessingResponse(
        success=result.success,
        items_extracted=len(result.extraction.products) if result.extraction else 0,
        items_matched=len(result.matched_products),
        error=result.error,
    )


@router.post("/{receipt_id}/confirm", response_model=ReceiptConfirmResponse)
async def confirm_receipt(
    receipt_id: UUID,
    confirm_request: ReceiptConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> ReceiptConfirmResponse:
    """Confirm extracted receipt items and create inventory.

    This endpoint allows the user to review, edit, and confirm the items
    extracted from a receipt. Confirmed items are then added to inventory
    with calculated expiry dates.

    Args:
        receipt_id: Receipt UUID to confirm.
        confirm_request: List of confirmed items to add to inventory.
        db: Database session.

    Returns:
        Confirmation result with number of inventory items created.

    Raises:
        HTTPException 404: If receipt not found.
        HTTPException 400: If product not found or validation fails.
    """
    # Get receipt
    receipt = await crud_receipt.get_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' not found",
        )

    try:
        items_created = 0

        for item in confirm_request.items:
            # Validate product exists
            stmt = select(ProductMaster).where(ProductMaster.id == item.product_id)
            result = await db.execute(stmt)
            product = result.scalar_one_or_none()

            if not product:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product '{item.product_id}' not found",
                )

            # Calculate expiry date
            expiry_date = item.purchase_date + timedelta(days=product.default_shelf_life_days)

            # Create inventory item
            inventory_item = InventoryItem(
                product_master_id=item.product_id,
                receipt_id=receipt_id,
                initial_quantity=item.quantity,
                current_quantity=item.quantity,
                unit=item.unit,
                status="sealed",
                purchase_date=item.purchase_date,
                expiry_date=expiry_date,
                expiry_source="calculated",
                location="main_fridge",  # Default location
            )

            db.add(inventory_item)
            items_created += 1

        # Update receipt status
        receipt.processing_status = "confirmed"
        await db.commit()

        # Broadcast confirmed status
        await broadcast_receipt_status(
            receipt_id=receipt.id,
            status="confirmed",
            items_extracted=receipt.items_extracted,
            items_matched=items_created
        )

        return ReceiptConfirmResponse(
            success=True,
            items_created=items_created,
            error=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        error_msg = f"Failed to confirm receipt: {str(e)}"
        return ReceiptConfirmResponse(
            success=False,
            items_created=0,
            error=error_msg,
        )
