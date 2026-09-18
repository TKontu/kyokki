"""API endpoints for Product CRUD operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.exceptions import handle_integrity_errors, reference_conflict_detail
from app.crud import product_master as crud_product
from app.db.session import get_db
from app.schemas.product_master import (
    ProductMasterCreate,
    ProductMasterResponse,
    ProductMasterUpdate,
    ProductMergeRequest,
    ProductMergeResponse,
)
from app.services.broadcast_helpers import broadcast_inventory_update
from app.services.off_service import (
    OffApiError,
    OffProductNotFoundError,
    enrich_product_from_off,
)
from app.services.product_merge import (
    MergeIntoItself,
    UnknownProduct,
    merge_products,
)

router = APIRouter()


@router.get("", response_model=list[ProductMasterResponse])
async def list_products(
    search: str | None = Query(None, description="Search by product name"),
    db: AsyncSession = Depends(get_db),
) -> list[ProductMasterResponse]:
    """Get all products with optional search filter."""
    products = await crud_product.get_products(db, search=search)
    return products


@router.get("/barcode/{barcode}", response_model=ProductMasterResponse)
async def lookup_by_barcode(
    barcode: str, db: AsyncSession = Depends(get_db)
) -> ProductMasterResponse:
    """Lookup a product by barcode/OFF product ID."""
    product = await crud_product.get_product_by_barcode(db, barcode)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with barcode '{barcode}' not found",
        )
    return product


@router.get("/{product_id}", response_model=ProductMasterResponse)
async def get_product(
    product_id: UUID, db: AsyncSession = Depends(get_db)
) -> ProductMasterResponse:
    """Get a specific product by ID."""
    product = await crud_product.get_product(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )
    return product


@router.post(
    "", response_model=ProductMasterResponse, status_code=status.HTTP_201_CREATED
)
async def create_product(
    product: ProductMasterCreate, db: AsyncSession = Depends(get_db)
) -> ProductMasterResponse:
    """Create a new product."""
    async with handle_integrity_errors():
        return await crud_product.create_product(db, product)


@router.patch("/{product_id}", response_model=ProductMasterResponse)
async def update_product(
    product_id: UUID,
    product_update: ProductMasterUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProductMasterResponse:
    """Update a product."""
    async with handle_integrity_errors():
        product = await crud_product.update_product(db, product_id, product_update)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a product, unless something still refers to it.

    Confirming a receipt writes a store_product_alias row per product, so a
    product that has ever been bought has a reference and answers 409 rather
    than the 500 it used to. H22 decides which of those should cascade instead.
    """
    references = await crud_product.references_to_product(db, product_id)
    if references:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=reference_conflict_detail(references),
        )

    async with handle_integrity_errors():
        deleted = await crud_product.delete_product(db, product_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )


@router.post("/{product_id}/merge", response_model=ProductMergeResponse)
async def merge_product(
    product_id: UUID,
    request: ProductMergeRequest,
    db: AsyncSession = Depends(get_db),
) -> ProductMergeResponse:
    """Fold a duplicate product into the one it duplicates, and delete it.

    This is the safe answer to "I cannot delete this product": `DELETE
    /products/{id}` refuses with 409 while anything still refers to the row, and
    a merge moves those references to the target instead of destroying them. The
    merged-away name stays a synonym of the target, so it keeps resolving.

    Returns:
        - 200: Merged; the body says what moved and what duplicate rows were dropped.
        - 400: The two ids are the same product.
        - 404: Either product does not exist.
    """
    try:
        async with handle_integrity_errors():
            result = await merge_products(db, product_id, request.target_id)
    except MergeIntoItself as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except UnknownProduct as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    target_name = str(result.target.canonical_name)
    for item in result.inventory_items:
        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="updated",
            current_quantity=item.current_quantity,
            status=item.status,
            product_name=target_name,
        )

    return ProductMergeResponse(
        source_id=result.source_id,
        source_name=result.source_name,
        target=ProductMasterResponse.model_validate(
            result.target, from_attributes=True
        ),
        moved=result.moved,
        dropped=result.dropped,
    )


@router.post("/enrich")
async def enrich_product(
    barcode: str = Query(
        ..., description="Product barcode to look up in Open Food Facts"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Enrich product from Open Food Facts API.

    If a product with the barcode already exists, it will be updated.
    Otherwise, a new product will be created with data from OFF.

    Returns:
        - 201: Product created from OFF data
        - 200: Existing product updated with OFF data
        - 404: Product not found in Open Food Facts
        - 503: Open Food Facts API unavailable
    """
    try:
        enriched_data = await enrich_product_from_off(barcode)

        async with handle_integrity_errors():
            product, created = await crud_product.enrich_product_from_off_data(
                db, enriched_data
            )

        response_data = ProductMasterResponse.model_validate(
            product, from_attributes=True
        ).model_dump(mode="json")

        if created:
            return JSONResponse(
                content=response_data, status_code=status.HTTP_201_CREATED
            )
        return JSONResponse(content=response_data, status_code=status.HTTP_200_OK)

    except OffProductNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product {e.barcode} not found in Open Food Facts database",
        ) from e
    except OffApiError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Open Food Facts API unavailable: {str(e)}",
        ) from e
