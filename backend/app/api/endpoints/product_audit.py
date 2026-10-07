"""Read-only audits of the catalog (CL8 L4)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.product_audit import ProductJoinAudit
from app.services.product_audit import audit_product_joins

router = APIRouter()


@router.get("/product-joins", response_model=ProductJoinAudit)
async def get_product_join_audit(
    db: AsyncSession = Depends(get_db),
) -> ProductJoinAudit:
    """List products whose items may have been joined to them wrongly. Writes nothing.

    A product is listed when its receipt-born items came in under two or more printed
    names (per store chain, normalised) and any of them joined without an exact key - a
    model pick (`selected`), no match at read time but a product at confirm (`none`), an
    unverified or model alias, or an alias learned at another chain - or when the lines'
    generic names differ. Each entry shows its printed groups (how they matched, the
    generic names read, how many items are still in stock, first and last purchase) and
    the reasons it was flagged. The least alike printed names come first
    (`min_similarity`, 0-1, used only to rank). Also lists every model-taught product
    name and every unverified alias with its use count, for review.

    Usage, read-only over HTTP (a read-scope token is enough when tokens are configured):

        curl -s -H "Authorization: Bearer $TOKEN" \\
            http://<host>:<port>/api/audit/product-joins | jq '.products[:5]'

    Review each listed product, then split the wrong items off it (product split).
    """
    return await audit_product_joins(db)
