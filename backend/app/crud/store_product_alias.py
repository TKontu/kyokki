"""CRUD operations for StoreProductAlias: the printed receipt names of a product."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store_product_alias import StoreProductAlias


async def aliases_for_product(
    db: AsyncSession, product_id: UUID
) -> list[StoreProductAlias]:
    """Every printed name that resolves to this product, by chain then name (H52)."""
    rows = (
        (
            await db.execute(
                select(StoreProductAlias)
                .where(StoreProductAlias.product_master_id == product_id)
                .order_by(StoreProductAlias.store_chain, StoreProductAlias.receipt_name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def delete_alias(db: AsyncSession, product_id: UUID, alias_id: UUID) -> bool:
    """Forget one printed name of this product. False when it is not this product's.

    Only the key goes: receipt lines already confirmed keep their products, and the next
    line printed this way is resolved afresh.
    """
    alias = await db.get(StoreProductAlias, alias_id)
    if alias is None or alias.product_master_id != product_id:
        return False
    await db.delete(alias)
    await db.commit()
    return True
