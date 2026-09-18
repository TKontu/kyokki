"""Resolving and learning the names that mean a product.

The key half of `docs/PRODUCT_RESOLUTION_SPEC.md`: a line resolves to a product through an
exact key, never through a similarity score. This module owns the key format and the two
operations on it - look a name up, and learn a new one.
"""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName

logger = get_logger(__name__)


def normalize_product_name(name: str | None) -> str:
    """The lookup key: casefolded, whitespace collapsed.

    Deliberately gentler than `normalize_receipt_name`, which also strips a trailing
    price because it keys *printed* names. These are catalog names.
    """
    return " ".join((name or "").split()).casefold()


async def product_for_name(db: AsyncSession, name: str | None) -> ProductMaster | None:
    """The product this name means, or None. An exact key, never a score.

    Falls back to the canonical name itself for rows written without a `product_name`
    row - the backfill migration covers everything that existed, but the fallback keeps
    resolution correct for anything that slips past `learn_product_name` later.
    """
    key = normalize_product_name(name)
    if not key:
        return None

    by_key = (
        (
            await db.execute(
                select(ProductMaster)
                .join(ProductName, ProductName.product_master_id == ProductMaster.id)
                .where(ProductName.name == key)
            )
        )
        .scalars()
        .first()
    )
    if by_key is not None:
        return by_key

    return (
        (
            await db.execute(
                select(ProductMaster)
                .where(func.lower(func.btrim(ProductMaster.canonical_name)) == key)
                .order_by(ProductMaster.created_at)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def known_names(
    db: AsyncSession, names: Iterable[str]
) -> dict[str, ProductMaster]:
    """Resolve many names at once, keyed by their normalised form.

    One query for a whole receipt instead of one per line.
    """
    keys = {normalize_product_name(name) for name in names}
    keys.discard("")
    if not keys:
        return {}
    rows = (
        await db.execute(
            select(ProductName.name, ProductMaster)
            .join(ProductMaster, ProductName.product_master_id == ProductMaster.id)
            .where(ProductName.name.in_(keys))
        )
    ).all()
    return {str(key): product for key, product in rows}


async def learn_product_name(
    db: AsyncSession,
    product: ProductMaster,
    name: str | None,
    source: str = "model",
) -> bool:
    """Record that ``name`` means ``product``. Returns True when a row was added.

    A name already claimed by another product is left alone: the first claim wins, and
    the cook resolves a genuine clash with a merge (spec §3.7). Re-learning a name the
    product already has is a no-op, so confirm can call this unconditionally.
    """
    key = normalize_product_name(name)
    if not key:
        return False

    existing = (
        (await db.execute(select(ProductName).where(ProductName.name == key)))
        .scalars()
        .first()
    )
    if existing is not None:
        if existing.product_master_id != product.id:
            logger.info(
                "Name already means another product; leaving it alone",
                extra={
                    "product_name": key,
                    "claimed_by": str(existing.product_master_id),
                    "offered": str(product.id),
                },
            )
        return False

    db.add(ProductName(product_master_id=product.id, name=key, source=source))
    await db.flush()
    return True
