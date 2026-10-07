"""Data access on `product_reassignment`: the record a split leaves so it can be undone (CL8)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_reassignment import ProductReassignment


async def record_reassignment(
    db: AsyncSession,
    *,
    from_product_id: UUID,
    to_product_id: UUID,
    target_created: bool,
    item_ids: list[UUID],
    keys: dict[str, Any],
) -> ProductReassignment:
    """Add the record of one split. Does not commit; the split owns the transaction."""
    row = ProductReassignment(
        from_product_id=from_product_id,
        to_product_id=to_product_id,
        target_created=target_created,
        item_ids=[str(item_id) for item_id in item_ids],
        keys=keys,
    )
    db.add(row)
    await db.flush()
    return row


async def get_reassignment_for_update(
    db: AsyncSession, reassignment_id: UUID
) -> ProductReassignment | None:
    """The record, locked, so two undos of one split run one after the other."""
    result = await db.execute(
        select(ProductReassignment)
        .where(ProductReassignment.id == reassignment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


def mark_undone(row: ProductReassignment) -> None:
    """Stamp the record as reversed; an undone split cannot be undone again."""
    record: Any = row
    record.undone_at = datetime.now(UTC)
