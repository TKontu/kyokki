import asyncio
import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .services.websockets import manager
from .core.config import settings
from .core.logging import setup_logging, get_logger
from .api.router import api_router
# from .middleware.logging import LoggingMiddleware  # TODO: Create if needed

async def redis_listener(app: FastAPI):
    """
    Listens to a Redis channel and broadcasts messages to WebSocket clients.
    """
    logger = get_logger("redis_listener")
    redis_client = redis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("updates")

    logger.info("Redis listener started. Waiting for messages...")
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                logger.info(
                    "Received message from Redis",
                    extra={
                        "operation": "redis_message_received",
                        "message_data": message['data'].decode('utf-8')
                    }
                )
                await manager.broadcast(message["data"].decode("utf-8"))
            await asyncio.sleep(0.1) # Short sleep to prevent high CPU usage
    except asyncio.CancelledError:
        logger.info("Redis listener cancelled.")
    except Exception as e:
        logger.error(f"Redis listener error: {str(e)}", exc_info=True)
    finally:
        logger.info("Closing Redis listener.")
        await pubsub.unsubscribe("updates")
        await pubsub.aclose()
        await redis_client.aclose()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging first
    setup_logging()
    logger = get_logger("startup")

    # Startup
    logger.info("Application starting up...")
    # Start the Redis listener as a background task
    listener_task = asyncio.create_task(redis_listener(app))
    yield
    # Shutdown
    logger.info("Application shutting down...")
    # Cancel the listener task and wait for it to finish
    listener_task.cancel()
    await listener_task

app = FastAPI(title="Kyokki API", lifespan=lifespan)

# Add logging middleware (TODO: uncomment when middleware is created)
# app.add_middleware(LoggingMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to Kyokki API"}

