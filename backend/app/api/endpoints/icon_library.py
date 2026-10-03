"""Icon curation (operator ask 2026-10-03): the cook marks a good generated icon
canonical, ready to submit to the repo's icon library.

"The generated -> canonical should be a feature of the 'develop' production build I use.
... during use more [icons] are generated and some are re-generated and after that updated
canonical [icons] can be submitted to the repo." Gated behind `ICON_CURATION_ENABLED`
(`backend/app/core/config.py`), false by default - this is the operator's own develop
build, not a cook-facing feature every deployment needs. The marking routes answer 404
when the setting is off, same as a route that does not exist; `status` always answers (it
is how the frontend knows whether to show the curation UI in the first place), and the
list and bundle routes are read-only and need no gate of their own - there is simply
nothing to list or zip once nothing can be marked.

Business logic (eligibility, the mark itself, the bundle) lives in
`app.services.icon_library`; this router is thin, same as the rest of the API.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AgentError
from app.core.config import settings
from app.crud import product_master as crud_product
from app.db.session import get_db
from app.models.product_master import ProductMaster
from app.services import icon_library

router = APIRouter()


class IconLibraryStatusResponse(BaseModel):
    """What the product sheet and Settings need to decide whether to show curation."""

    curation_enabled: bool
    library_count: int = Field(
        ..., description="How many products the repo's icon library already covers"
    )
    marked_count: int = Field(
        ..., description="How many products are currently marked canonical"
    )


class IconMarkEntry(BaseModel):
    """One marked product, for Settings' "Canonical icons" list.

    `marked_at` is always set in the list (`GET /marks` only ever returns marked
    products); the mark and unmark routes reuse this same shape for their own response,
    where unmark's answer is null - the product right after its mark was dropped.
    """

    id: UUID
    name: str
    icon_version: int | None
    marked_at: datetime | None


def _entry(product: ProductMaster) -> IconMarkEntry:
    return IconMarkEntry(
        id=product.id,  # type: ignore[arg-type]
        name=str(product.canonical_name),
        icon_version=product.icon_version,
        marked_at=product.icon_canonical_at,  # type: ignore[arg-type]
    )


def _require_curation_enabled() -> None:
    if not settings.ICON_CURATION_ENABLED:
        raise AgentError("not_found", "Icon curation is not enabled on this server")


@router.get("/status", response_model=IconLibraryStatusResponse)
async def get_status(
    db: AsyncSession = Depends(get_db),
) -> IconLibraryStatusResponse:
    """Always answers, curation on or off - the frontend uses `curation_enabled` itself to
    decide whether to show any of this."""
    return IconLibraryStatusResponse(
        curation_enabled=settings.ICON_CURATION_ENABLED,
        library_count=icon_library.library_count(),
        marked_count=await crud_product.count_marked_icons(db),
    )


@router.put("/marks/{product_id}", response_model=IconMarkEntry)
async def mark_icon(
    product_id: UUID, db: AsyncSession = Depends(get_db)
) -> IconMarkEntry:
    """The cook's "Keep as canonical" on the product sheet.

    Returns:
        - 404: curation is disabled on this server, or no such product.
        - 409: the icon is not a ready, actually-generated image with no emoji win
          (`services.icon_library.is_markable`).
    """
    _require_curation_enabled()
    try:
        product = await icon_library.mark_canonical(db, product_id)
    except icon_library.IconNotMarkable as exc:
        raise AgentError("conflict", str(exc)) from exc
    if product is None:
        raise AgentError("not_found", f"Product with ID '{product_id}' not found")
    return _entry(product)


@router.delete("/marks/{product_id}", response_model=IconMarkEntry)
async def unmark_icon(
    product_id: UUID, db: AsyncSession = Depends(get_db)
) -> IconMarkEntry:
    """Undo a mark. A no-op, not an error, on a product that was never marked.

    Returns:
        - 404: curation is disabled on this server, or no such product.
    """
    _require_curation_enabled()
    product = await icon_library.unmark_canonical(db, product_id)
    if product is None:
        raise AgentError("not_found", f"Product with ID '{product_id}' not found")
    return _entry(product)


@router.get("/marks", response_model=list[IconMarkEntry])
async def list_marks(db: AsyncSession = Depends(get_db)) -> list[IconMarkEntry]:
    """Every currently marked product, newest mark first - Settings' own list."""
    products = await crud_product.marked_icons(db)
    return [_entry(product) for product in products]


@router.get(
    "/bundle.zip",
    responses={200: {"content": {"application/zip": {}}, "description": "The bundle"}},
)
async def download_bundle(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    """Every marked icon as one zip: `icon_library/<slug>.png` plus an `index.json`
    fragment in the library's own entry format - `scripts/apply_icon_bundle.py` merges it
    into the repo for a PR.
    """
    products = await crud_product.canonical_icons(db)
    host = request.url.hostname or "unknown-host"
    if request.url.port:
        host = f"{host}:{request.url.port}"
    data = icon_library.build_bundle(products, host=host)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=icon_bundle.zip"},
    )
