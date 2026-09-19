"""Folding one product into another: the repair for a duplicate catalog entry.

`docs/PRODUCT_RESOLUTION_SPEC.md` §3.7. Duplicates are prevented at the schema and
repairable by merge (§2, principle 5): the unique index on the canonical name stops
new exact duplicates, and near-duplicates - "Ground beef" and "Minced beef" are the
spec's own example - are fixed here by the cook, never by a script.

This is also the safe answer to "I cannot delete this product". `DELETE /products/{id}`
answers 409 while anything still refers to the row (`crud.product_master.references_to_product`),
which in practice is every product that has ever been bought. Those references are
exactly what a merge moves rather than destroys.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.crud.product_master import MergeResult
from app.services.expiry_recompute import recompute_expiry_for_product

logger = get_logger(__name__)


class ProductMergeError(Exception):
    """A merge refused before anything moved."""


class UnknownProduct(ProductMergeError):
    """One side of the merge does not exist."""

    def __init__(self, product_id: UUID) -> None:
        super().__init__(f"Product with ID '{product_id}' not found")
        self.product_id = product_id


class MergeIntoItself(ProductMergeError):
    """Source and target are the same product."""

    def __init__(self, product_id: UUID) -> None:
        super().__init__(
            f"Product '{product_id}' cannot be merged into itself; "
            "pick the product it duplicates."
        )
        self.product_id = product_id


async def merge_products(
    db: AsyncSession, source_id: UUID, target_id: UUID
) -> MergeResult:
    """Merge ``source_id`` into ``target_id`` and delete the source.

    Both checks happen before any row moves, so a refusal leaves the catalog
    untouched. Merging a product into itself would delete the only copy of it
    after re-pointing everything at itself, so it is refused rather than treated
    as a no-op the cook cannot see.

    Raises:
        MergeIntoItself: Source and target are the same product.
        UnknownProduct: Either side does not exist.
    """
    if source_id == target_id:
        raise MergeIntoItself(source_id)

    source = await crud_product.get_product(db, source_id)
    if source is None:
        raise UnknownProduct(source_id)
    target = await crud_product.get_product(db, target_id)
    if target is None:
        raise UnknownProduct(target_id)

    try:
        result = await crud_product.merge_product_rows(db, source, target)
        # The moved stock now belongs to a product with its own shelf life, so its dates
        # were worked out from a figure that no longer applies to it (Q12).
        await recompute_expiry_for_product(db, target)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Products merged",
        extra={
            "source_id": str(source_id),
            "target_id": str(target_id),
            "moved": result.moved,
            "dropped": result.dropped,
        },
    )
    return result
