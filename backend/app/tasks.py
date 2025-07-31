from app.core.celery_app import celery_app
from app.services.ollama import ollama_service
from app.db.session import AsyncSessionLocal
from app import crud, schemas
import asyncio

@celery_app.task(acks_late=True)
def analyze_image_task(image_path: str):
    """
    Celery task to analyze an image and save the result to the database.
    """
    async def main():
        async with AsyncSessionLocal() as db:
            analysis_result = await ollama_service.analyze_image(image_path)
            
            item_in = schemas.ItemCreate(
                product_name=analysis_result.get("product_name"),
                category=analysis_result.get("category"),
                expiry_date=analysis_result.get("expiry_date"),
                confidence_score=analysis_result.get("confidence_score"),
                image_path=image_path
            )
            await crud.item.create(db=db, obj_in=item_in)

    asyncio.run(main())
    return {"status": "complete", "image_path": image_path}
