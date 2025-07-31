import uuid
import aiofiles
from typing import List, Any
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.db import session
from app.tasks import analyze_image_task

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
    Retrieve items that are not soft-deleted.
    """
    items = await crud.item.get_multi(db, skip=skip, limit=limit)
    return [item for item in items if not item.is_deleted]


@router.post("/analyze", status_code=202)
async def analyze_item(
    *,
    file: UploadFile = File(...)
) -> Any:
    """
    Accept an image for background analysis.
    """
    file_extension = file.filename.split(".")[-1]
    image_name = f"{uuid.uuid4()}.{file_extension}"
    image_path_in_container = f"/app/data/images/raw/{image_name}"
    
    async with aiofiles.open(image_path_in_container, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    task = analyze_image_task.delay(image_path_in_container)
    return {"task_id": task.id, "status": "processing"}


@router.put("/{id}", response_model=schemas.Item)
async def update_item(
    *,
    db: AsyncSession = Depends(get_db),
    id: uuid.UUID,
    item_in: schemas.ItemUpdate,
) -> Any:
    """
    Update an item.
    """
    item = await crud.item.get(db=db, id=id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item = await crud.item.update(db=db, db_obj=item, obj_in=item_in)
    return item


@router.delete("/{id}", response_model=schemas.Item)
async def delete_item(
    *,
    db: AsyncSession = Depends(get_db),
    id: uuid.UUID,
) -> Any:
    """
    Soft delete an item.
    """
    item = await crud.item.soft_delete(db=db, id=id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/{id}/restore", response_model=schemas.Item)
async def restore_item(
    *,
    db: AsyncSession = Depends(get_db),
    id: uuid.UUID,
) -> Any:
    """
    Restore a soft-deleted item.
    """
    item = await crud.item.restore(db=db, id=id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
