"""Quick add: stock added by hand from the iPad in one transaction (MVP-S3)."""

from dataclasses import dataclass
from datetime import date
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import inventory_item as crud_inventory
from app.models.inventory_item import InventoryItem
from app.schemas.inventory_item import QuickAddRequest
from app.services.generic_products import ProductResolver, build_inventory_item

logger = get_logger(__name__)


@dataclass(frozen=True)
class QuickAddResult:
    item: InventoryItem
    product_created: bool


async def quick_add(db: AsyncSession, request: QuickAddRequest) -> QuickAddResult:
    """Find or create the generic product and add a sealed inventory item for it.

    Raises:
        InvalidProductRequest: unknown product, or a new product without a valid category.
    """
    try:
        product, created = await ProductResolver(db).resolve(
            product_id=request.product_id,
            name=request.name,
            category=request.category,
            unit=request.unit,
            quantity=request.quantity,
        )
        item = build_inventory_item(
            product,
            quantity=request.quantity,
            unit=request.unit,
            purchase_date=request.purchase_date or date.today(),
            expiry_date=request.expiry_date,
            location=request.location,
        )
        db.add(item)
        await db.commit()
        # Reload with the product so the response has product and category names
        loaded = await crud_inventory.get_inventory_item(db, cast(UUID, item.id))
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Quick add",
        extra={
            "inventory_item_id": str(item.id),
            "product_id": str(product.id),
            "product_created": created,
        },
    )
    return QuickAddResult(item=cast(InventoryItem, loaded), product_created=created)
