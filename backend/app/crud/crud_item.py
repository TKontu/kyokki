from datetime import datetime
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate


class CRUDItem(CRUDBase[Item, ItemCreate, ItemUpdate]):
    async def soft_delete(self, db: AsyncSession, *, id: UUID) -> Optional[Item]:
        db_obj = await self.get(db=db, id=id)
        if db_obj:
            db_obj.is_deleted = True
            db_obj.deleted_at = datetime.utcnow()
            await db.commit()
            await db.refresh(db_obj)
        return db_obj

    async def restore(self, db: AsyncSession, *, id: UUID) -> Optional[Item]:
        db_obj = await self.get(db=db, id=id)
        if db_obj:
            db_obj.is_deleted = False
            db_obj.deleted_at = None
            await db.commit()
            await db.refresh(db_obj)
        return db_obj


item = CRUDItem(Item)