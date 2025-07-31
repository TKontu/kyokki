import asyncio
import json
from app.core.celery_app import celery_app
from app.services.ollama import ollama_service
from app.services.websockets import manager
from app.db.session import AsyncSessionLocal
from app import crud, schemas
from app.schemas.item import Item  # Import the specific schema for serialization

@celery_app.task(acks_late=True)
def analyze_image_task(image_path: str):
    """
    Celery task to analyze an image, save the result, and broadcast an update.
    """
    async def main():
        async with AsyncSessionLocal() as db:
            # Analyze the image
            analysis_result = await ollama_service.analyze_image(image_path)
            
            # Create the item in the database
            item_in = schemas.ItemCreate(
                product_name=analysis_result.get("product_name"),
                category=analysis_result.get("category"),
                expiry_date=analysis_result.get("expiry_date"),
                confidence_score=analysis_result.get("confidence_score"),
                image_path=image_path
            )
            new_item = await crud.item.create(db=db, obj_in=item_in)

            # Serialize the new item to a Pydantic model and then to JSON
            item_data = Item.from_orm(new_item).json()
            
            # Broadcast the new item data
            await manager.broadcast(item_data)

    # Run the async main function
    asyncio.run(main())
    
    return {"status": "complete", "image_path": image_path}