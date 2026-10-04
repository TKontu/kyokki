"""API endpoints for Receipt upload and management."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import handle_integrity_errors
from app.core.logging import get_logger
from app.crud import receipt as crud_receipt
from app.db.session import get_db
from app.schemas.receipt import (
    ExtractedItem,
    ReanalyseLineRequest,
    ReceiptAuditResponse,
    ReceiptConfirmRequest,
    ReceiptConfirmResponse,
    ReceiptResponse,
    ReceiptStatus,
    ReceiptSummary,
)
from app.services import (
    receipt_audit,
    receipt_confirm,
    receipt_line_reanalyse,
    receipt_queue,
)
from app.services.receipt_ingest import (
    ReceiptTooLarge,
    UnsupportedReceiptType,
    ingest_receipt_file,
)
from app.services.shelf_life_on_create import (
    schedule_estimates,
)

logger = get_logger(__name__)

router = APIRouter()

# Where a share lands (frontier item 10). The scan page renders the failure note, so
# these paths are a contract with the frontend.
SHARE_FAILED_LOCATION = "/scan?shared=failed"
SHARE_MANY_LOCATION = "/receipts"


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
        HTTPException 413: If the file is larger than MAX_RECEIPT_UPLOAD_BYTES.
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
    except ReceiptTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
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


@router.post("/share", status_code=status.HTTP_303_SEE_OTHER)
async def share_receipts(
    receipts: list[UploadFile] = File(default=[]),
    title: str | None = Form(None),
    text: str | None = Form(None),
    url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Receive receipts shared to the installed PWA (Android Web Share Target).

    The browser navigates here with a multipart form post, so the answer is a 303 to a
    page: one accepted receipt opens its review page, several open the receipt list, and
    none lands on the scan page with a failure note. A file of an unsupported type or over
    the size limit is skipped without stopping the others; a file already received counts
    as accepted and opens the existing receipt. ``title``, ``text`` and ``url`` are what
    Android sends alongside the files; they are accepted and ignored.
    """
    accepted: list[str] = []
    for upload in receipts:
        content = await upload.read()
        content_type = upload.content_type or ""
        try:
            result = await ingest_receipt_file(
                db,
                content=content,
                filename=upload.filename or "receipt",
                content_type=content_type,
            )
        except (UnsupportedReceiptType, ReceiptTooLarge) as exc:
            logger.info(
                "Shared receipt file skipped",
                extra={
                    "reason": type(exc).__name__,
                    "content_type": content_type or "unknown",
                    "size_bytes": len(content),
                },
            )
            continue
        receipt_id = str(result.receipt.id)
        if receipt_id not in accepted:
            accepted.append(receipt_id)

    if len(accepted) == 1:
        location = f"/receipt/{accepted[0]}"
    elif accepted:
        location = SHARE_MANY_LOCATION
    else:
        location = SHARE_FAILED_LOCATION
    return RedirectResponse(location, status_code=status.HTTP_303_SEE_OTHER)


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


@router.get("/{receipt_id}/file")
async def get_receipt_file(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve the receipt's original upload: the image or PDF the OCR pipeline read (Q28).

    Resolved only through the stored row - never a path the caller names - and only when
    it stays inside the upload directory and the file is still there.

    Raises:
        HTTPException 404: No such receipt, or its file is gone.
    """
    receipt = await crud_receipt.get_receipt(db, receipt_id)
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' not found",
        )
    path = receipt_audit.resolve_receipt_file(receipt)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt '{receipt_id}' has no file",
        )
    return FileResponse(
        path,
        media_type=receipt_audit.content_type_for(path),
        headers={
            "Content-Disposition": f'inline; filename="{path.name}"',
            "Cache-Control": "private, max-age=0, must-revalidate",
        },
    )


@router.get("/{receipt_id}/audit", response_model=ReceiptAuditResponse)
async def get_receipt_audit(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReceiptAuditResponse:
    """Everything the cook can check about how a receipt became stock (Q28).

    Available for any processing status, confirmed included: the metadata, the OCR text,
    the model's raw answer when one was stored, and each printed line's outcome.

    Raises:
        HTTPException 404: No such receipt.
    """
    try:
        return await receipt_audit.build_receipt_audit(db, receipt_id)
    except receipt_audit.ReceiptNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get("", response_model=list[ReceiptSummary])
async def list_receipts(
    status: ReceiptStatus | None = None,
    store: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ReceiptSummary]:
    """Get a page of receipts, newest first.

    The response leaves out the OCR text and the extracted items: the iPad polls this list,
    and the review page fetches the receipt it opens.

    Args:
        status: Optional filter by processing status; unknown values are rejected (422).
        store: Optional filter by store_chain.
        limit: Page size, 1-200.
        offset: How many of the newest receipts to skip.
        db: Database session.

    Returns:
        List of receipt summaries sorted by created_at (most recent first).
    """
    await receipt_queue.fail_stale(db)
    receipts = await crud_receipt.get_receipts(
        db,
        status=status,
        store_chain=store,
        limit=limit,
        offset=offset,
    )
    return [ReceiptSummary.model_validate(r) for r in receipts]


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

    A receipt read by the heuristic fallback (MVP-R3b) can also be re-queued for the model
    until it is confirmed.

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
    structured: dict[str, Any] = (
        receipt.ocr_structured if isinstance(receipt.ocr_structured, dict) else {}
    )
    # A completed read is worth repeating when it produced nothing usable: the
    # heuristic parser gives no categories or generic names, and an extraction
    # with no lines at all (an image-only PDF that never reached OCR) left the
    # cook with a receipt that could be neither re-read nor finished.
    empty_read = (receipt.items_extracted or 0) == 0
    rereadable = receipt.processing_status == ReceiptStatus.COMPLETED and (
        structured.get("method") == "heuristic" or empty_read
    )
    if (
        receipt.processing_status in (ReceiptStatus.COMPLETED, ReceiptStatus.CONFIRMED)
        and not rereadable
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt was already read",
        )

    try:
        await receipt_queue.enqueue(db, receipt)
    except receipt_queue.NotEnqueueable as exc:
        # Something changed the row between the read above and the queue write -
        # confirm holds a row lock while it sets `confirmed`.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return ReceiptResponse.model_validate(receipt)


@router.post("/{receipt_id}/confirm", response_model=ReceiptConfirmResponse)
async def confirm_receipt(
    receipt_id: UUID,
    confirm_request: ReceiptConfirmRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> ReceiptConfirmResponse:
    """Confirm reviewed receipt items: create inventory, generic products and store aliases.

    Items not sent are skipped. The whole confirm is one transaction. The products it
    created are estimated in the background, in one request, once this has answered (Q19).

    Raises:
        HTTPException 404: Receipt not found.
        HTTPException 409: Receipt already confirmed or not read yet.
        HTTPException 400: An item names an unknown product, line or category.
    """
    try:
        async with handle_integrity_errors():
            result = await receipt_confirm.confirm_receipt(
                db,
                receipt_id,
                confirm_request.items,
                confirm_request.non_food_indexes,
            )
    except receipt_confirm.ReceiptNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except receipt_confirm.ReceiptNotConfirmable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except receipt_confirm.InvalidConfirmItem as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    schedule_estimates(background_tasks, result.created_product_ids)
    return ReceiptConfirmResponse(
        success=True,
        items_created=result.items_created,
        products_created=result.products_created,
        aliases_learned=result.aliases_learned,
        error=None,
    )


@router.post("/{receipt_id}/lines/{line_id}/reanalyse", response_model=ExtractedItem)
async def reanalyse_receipt_line(
    receipt_id: UUID,
    line_id: UUID,
    request: ReanalyseLineRequest,
    db: AsyncSession = Depends(get_db),
) -> ExtractedItem:
    """Re-ask the model for one receipt line, with the cook's optional hint (Q38).

    Updates only this line's generic name, category and match. Nothing is learned: no
    alias, synonym or product is created or changed - only confirm does that.

    Raises:
        HTTPException 404: No such receipt, or no such line on it.
        HTTPException 409: The receipt is not reviewable (confirmed, or not read yet).
        HTTPException 400: The hint is too long.
        HTTPException 502: The model answered, but not usably.
        HTTPException 503: The model gateway could not be reached or rejected the key.
        HTTPException 504: The model did not answer within its budget.
    """
    try:
        async with handle_integrity_errors():
            return await receipt_line_reanalyse.reanalyse_line(
                db, receipt_id, line_id, request.hint
            )
    except receipt_line_reanalyse.ReceiptNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except receipt_line_reanalyse.LineNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except receipt_line_reanalyse.ReceiptNotReanalysable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except receipt_line_reanalyse.InvalidHint as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except receipt_line_reanalyse.InvalidModelAnswer as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except receipt_line_reanalyse.ReanalyseUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except receipt_line_reanalyse.ReanalyseTimedOut as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
