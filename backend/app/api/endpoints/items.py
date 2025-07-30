from typing import List, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.db import session

router = APIRouter()


async def get_db():
    async with session.AsyncSessionLocal() as db:
        yield db


@router.get("/", response_model=List[schemas.Item])
async def read_items(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve items.
    """
    items = await crud.item.get_multi(db, skip=skip, limit=limit)
    return items
