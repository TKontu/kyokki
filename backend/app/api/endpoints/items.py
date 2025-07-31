import uuid
import aiofiles
from typing import List, Any
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, models, schemas
from app.db import session
from app.services.ollama import ollama_service

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


@router.post("/analyze", response_model=schemas.Item)
async def analyze_item(
    *,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...)
) -> Any:
    """
    Analyze a new item by uploading an image.
    """
    # 1. Save the uploaded file
    file_extension = file.filename.split(".")[-1]
    image_name = f"{uuid.uuid4()}.{file_extension}"
    image_path = f"/app/data/images/raw/{image_name}"
    
    async with aiofiles.open(image_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    # 2. Analyze the image with Ollama
    analysis_result = await ollama_service.analyze_image(image_path)

    # 3. Create the item in the database
    item_in = schemas.ItemCreate(
        product_name=analysis_result.get("product_name", "Unknown"),
        category=analysis_result.get("category", "Unknown"),
        image_path=image_path
    )
    item = await crud.item.create(db=db, obj_in=item_in)
    return item