from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.crud.base import CRUDBase
from app.models.shopping_list_item import ShoppingListItem
from app.schemas.shopping_list_item import ShoppingListItemCreate, ShoppingListItemUpdate


class CRUDShoppingListItem(CRUDBase[ShoppingListItem, ShoppingListItemCreate, ShoppingListItemUpdate]):
    """CRUD operations for shopping list items."""

    async def get_all(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        priority: str | None = None,
        is_purchased: bool | None = None,
        include_purchased: bool = False,
    ) -> list[ShoppingListItem]:
        """Get all shopping list items with optional filtering.

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            priority: Filter by priority (urgent, normal, low)
            is_purchased: Filter by purchase status
            include_purchased: Whether to include purchased items (default: False)

        Returns:
            List of shopping list items
        """
        query = select(ShoppingListItem).options(joinedload(ShoppingListItem.product_master))

        # Default: exclude purchased items unless explicitly requested
        if not include_purchased and is_purchased is None:
            query = query.where(ShoppingListItem.is_purchased == False)
        elif is_purchased is not None:
            query = query.where(ShoppingListItem.is_purchased == is_purchased)

        if priority:
            query = query.where(ShoppingListItem.priority == priority)

        # Order by priority (urgent first), then by added date
        # Use CASE to map priority to numeric values for proper sorting
        from sqlalchemy import case
        priority_order = case(
            (ShoppingListItem.priority == "urgent", 1),
            (ShoppingListItem.priority == "normal", 2),
            (ShoppingListItem.priority == "low", 3),
            else_=4
        )

        query = query.order_by(
            priority_order.asc(),  # 1=urgent, 2=normal, 3=low
            ShoppingListItem.added_at.asc(),  # oldest first within same priority
        )

        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().unique().all())

    async def get_urgent_items(self, db: AsyncSession) -> list[ShoppingListItem]:
        """Get all urgent items that are not yet purchased.

        Args:
            db: Database session

        Returns:
            List of urgent shopping list items
        """
        return await self.get_all(db, priority="urgent", is_purchased=False)

    async def mark_purchased(
        self, db: AsyncSession, *, item_id: UUID, purchased: bool = True
    ) -> ShoppingListItem | None:
        """Mark a shopping list item as purchased or unpurchased.

        Args:
            db: Database session
            item_id: Shopping list item ID
            purchased: Whether the item is purchased

        Returns:
            Updated shopping list item or None if not found
        """
        from datetime import datetime, timezone

        item = await self.get(db, id=item_id)
        if not item:
            return None

        item.is_purchased = purchased
        item.purchased_at = datetime.now(timezone.utc) if purchased else None

        await db.commit()
        await db.refresh(item)
        return item

    async def delete_purchased(self, db: AsyncSession) -> int:
        """Delete all purchased items from the shopping list.

        Args:
            db: Database session

        Returns:
            Number of items deleted
        """
        stmt = delete(ShoppingListItem).where(ShoppingListItem.is_purchased == True)
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount

    async def get_by_product(
        self, db: AsyncSession, *, product_master_id: UUID
    ) -> list[ShoppingListItem]:
        """Get all shopping list items for a specific product.

        Args:
            db: Database session
            product_master_id: Product master ID

        Returns:
            List of shopping list items
        """
        query = (
            select(ShoppingListItem)
            .where(ShoppingListItem.product_master_id == product_master_id)
            .where(ShoppingListItem.is_purchased == False)
            .options(joinedload(ShoppingListItem.product_master))
        )
        result = await db.execute(query)
        return list(result.scalars().unique().all())


shopping_list_item = CRUDShoppingListItem(ShoppingListItem)
