import asyncio
import json
import redis.asyncio as redis
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.celery_app import celery_app
from app.services.ollama import ollama_service
from app import crud, schemas
from app.schemas.item import Item
from app.core.config import settings

@celery_app.task(acks_late=True)
def analyze_image_task(image_path: str):
    """
    Celery task to analyze an image, save the result, and publish an update to Redis.
    This task creates its own database engine to avoid event loop conflicts with Celery.
    """
    async def main():
        # Create a new database engine and session for this task's event loop
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        TaskSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
        )

        # Initialize Redis client
        redis_client = redis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")

        async with TaskSessionLocal() as db:
            # Analyze the image
            analysis_result = await ollama_service.analyze_image(image_path)
            
            # Convert expiry_date string to date object
            expiry_date_str = analysis_result.get("expiry_date")
            expiry_date_obj = None
            if expiry_date_str:
                try:
                    expiry_date_obj = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    expiry_date_obj = None

            # Create the item in the database
            item_in = schemas.ItemCreate(
                product_name=analysis_result.get("product_name"),
                category=analysis_result.get("category"),
                expiry_date=expiry_date_obj,
                confidence_score=analysis_result.get("confidence_score"),
                image_path=image_path
            )
            new_item = await crud.item.create(db=db, obj_in=item_in)

            # Serialize the new item to a Pydantic model and then to JSON
            item_data = Item.from_orm(new_item).json()
            
            # Publish the new item data to the 'item_updates' channel
            await redis_client.publish("item_updates", item_data)

        # Close connections
        await redis_client.close()
        await engine.dispose()

    # Run the async main function
    asyncio.run(main())
    
    return {"status": "complete", "image_path": image_path}


