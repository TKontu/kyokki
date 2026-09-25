"""API endpoints for Product CRUD operations."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.stock import IdempotencyKeyHeader, claim_request, replayed
from app.api.errors import AgentError
from app.api.exceptions import handle_integrity_errors, reference_conflict_detail
from app.crud import product_master as crud_product
from app.crud import store_product_alias as crud_alias
from app.crud.product_master import MovedInventoryItem
from app.db.session import get_db
from app.schemas.product_master import (
    CatalogEstimateChange,
    CatalogEstimateResponse,
    ProductMasterCreate,
    ProductMasterResponse,
    ProductMasterUpdate,
    ProductMergeRequest,
    ProductMergeResponse,
)
from app.schemas.product_names import (
    PrintedNameEntry,
    ProductNameEntry,
    ProductNamesResponse,
)
from app.schemas.stock import ResolveResponse, TeachNameRequest
from app.services import product_lookup
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_product_update,
)
from app.services.catalog_estimates import refresh_catalog_shelf_lives
from app.services.expiry_recompute import recompute_expiry_for_product
from app.services.llm_extractor import LLMExtractionError
from app.services.off_service import (
    OffApiError,
    OffProductNotFoundError,
    enrich_product_from_off,
)
from app.services.product_lookup import NameTaken, ProductNotFound
from app.services.product_merge import (
    MergeIntoItself,
    UnknownProduct,
    merge_products,
)
from app.services.product_names import (
    CanonicalName,
    UnknownName,
    forget_product_name,
    names_for_product,
)

router = APIRouter()

TEACH_ROUTE = "POST /api/products/{product_id}/names"


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


# Declared before `/{product_id}`, which would otherwise take "resolve" for an id and answer 422
@router.get("/resolve", response_model=ResolveResponse)
async def resolve_product_name(
    name: str = Query(..., min_length=1, description="The name to resolve"),
    db: AsyncSession = Depends(get_db),
) -> ResolveResponse:
    """Which product a name means (AG2): an exact hit only, never a guess.

    `match` is set only when the name is a product's canonical or learned name. `candidates`
    are the products most like it, to choose from; `suggestion` is the normalised name to
    create when nothing matched.
    """
    return await product_lookup.resolve(db, name)


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
    """Update a product.

    Correcting a shelf life moves the stock that was dated by the old one (Q12): a date
    the cook typed is left alone, and so is anything already gone from the kitchen.
    """
    async with handle_integrity_errors():
        product = await crud_product.update_product(db, product_id, product_update)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )

    changed = product_update.model_dump(exclude_unset=True)
    if "default_shelf_life_days" in changed or "category" in changed:
        moved = await recompute_expiry_for_product(db, product)
        await db.commit()
        await _announce(moved, str(product.canonical_name))

    await broadcast_product_update(
        product_id, action="updated", product_name=str(product.canonical_name)
    )
    return product


@router.get("/{product_id}/names", response_model=ProductNamesResponse)
async def list_product_names(
    product_id: UUID, db: AsyncSession = Depends(get_db)
) -> ProductNamesResponse:
    """The names and printed receipt names that resolve to this product (H52)."""
    product = await crud_product.get_product(db, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found",
        )
    names = await names_for_product(db, product_id)
    aliases = await crud_alias.aliases_for_product(db, product_id)
    return ProductNamesResponse(
        names=[_name_entry(row) for row in names],
        printed=[_printed_entry(alias) for alias in aliases],
    )


@router.post(
    "/{product_id}/names",
    response_model=ProductNameEntry,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": ProductNameEntry, "description": "Already its name"}},
)
async def teach_name(
    product_id: UUID,
    body: TeachNameRequest,
    request: Request,
    idempotency_key: str | None = IdempotencyKeyHeader,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Teach a product a name, as the cook's word (AG2). 201 learned, 200 already its name.

    Errors: 404 `not_found` (no such product), 409 `conflict` (the name already means
    another product - merge them instead - or the Idempotency-Key was reused with another
    body).
    """
    claim = await claim_request(
        request, idempotency_key, TEACH_ROUTE, product_id=product_id
    )
    if (stored := await replayed(db, claim)) is not None:
        return stored
    try:
        async with handle_integrity_errors():
            taught = await product_lookup.teach_name(
                db, product_id, body.name, claim=claim
            )
    except ProductNotFound as exc:
        raise AgentError("not_found", str(exc)) from exc
    except NameTaken as exc:
        raise AgentError(
            "conflict",
            str(exc),
            product_id=str(exc.owner_id),
            product_name=exc.owner_name,
        ) from exc

    if taught.created:
        await broadcast_product_update(product_id, action="updated")
    return JSONResponse(
        content=taught.entry.model_dump(mode="json"), status_code=taught.status_code
    )


@router.delete("/{product_id}/names/{name_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_name(
    product_id: UUID, name_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Stop a learned name meaning this product. The canonical name answers 409."""
    try:
        async with handle_integrity_errors():
            await forget_product_name(db, product_id, name_id)
    except UnknownName:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This product has no such name",
        ) from None
    except CanonicalName:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product's own name cannot be removed; rename the product instead",
        ) from None
    await broadcast_product_update(product_id, action="name_forgotten")


@router.delete(
    "/{product_id}/aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def forget_printed_name(
    product_id: UUID, alias_id: UUID, db: AsyncSession = Depends(get_db)
) -> None:
    """Stop a printed receipt name resolving to this product (H52)."""
    async with handle_integrity_errors():
        deleted = await crud_alias.delete_alias(db, product_id, alias_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This product has no such printed name",
        )
    await broadcast_product_update(product_id, action="alias_forgotten")


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


def _name_entry(row: Any) -> ProductNameEntry:
    """A `product_name` row as the editor lists it; `Any` for the Column-typed model."""
    return ProductNameEntry(
        id=row.id,
        name=row.name,
        source=row.source,
        removable=row.source != "canonical",
    )


def _printed_entry(alias: Any) -> PrintedNameEntry:
    """A `store_product_alias` row as the editor lists it."""
    return PrintedNameEntry(
        id=alias.id,
        store_chain=alias.store_chain,
        receipt_name=alias.receipt_name,
        source=alias.source,
        verified=alias.manually_verified,
        occurrence_count=alias.occurrence_count,
        last_seen=alias.last_seen,
    )


async def _announce(items: list[MovedInventoryItem], product_name: str) -> None:
    """Tell every open iPad that these items now expire on a different day (Q12)."""
    for item in items:
        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="updated",
            current_quantity=item.current_quantity,
            status=item.status,
            product_name=product_name,
        )


@router.post("/estimate", response_model=CatalogEstimateResponse)
async def estimate_catalog_shelf_lives(
    apply: bool = Query(
        False,
        description="Write the changes. Omit for a dry run, which is the default.",
    ),
    db: AsyncSession = Depends(get_db),
) -> CatalogEstimateResponse:
    """Re-estimate the shelf lives nobody ever chose (Q11).

    `default_shelf_life_days` is NOT NULL, so creating a product had to invent a
    number and took its category's blanket figure. Those placeholders are the only
    candidates here: a shelf life the cook set is never sent to the model, and one
    the model already estimated is left alone.

    A dry run by default, because this walks the whole catalog in one go. Call it
    again with `apply=true` once the proposed numbers have been looked at.

    Returns:
        - 200: What would change, or what did.
        - 503: The model gateway could not be reached, or answered unusably.
          Nothing is written in that case, including by a partly-finished batch.
    """
    try:
        result = await refresh_catalog_shelf_lives(db, apply=apply)
    except LLMExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not estimate shelf lives: {exc}",
        ) from exc

    # Applying changes what every iPad shows, so say so (CLAUDE.md's broadcast rule).
    for item in result.moved:
        await broadcast_inventory_update(
            inventory_item_id=item.id,
            action="updated",
            current_quantity=item.current_quantity,
            status=item.status,
        )

    return CatalogEstimateResponse(
        considered=result.considered,
        answered=result.answered,
        applied=result.applied,
        items_redated=len(result.moved),
        changes=[
            CatalogEstimateChange.model_validate(change, from_attributes=True)
            for change in result.changes
        ],
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
