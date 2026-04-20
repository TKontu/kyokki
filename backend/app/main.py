import asyncio
import contextlib
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .core.config import settings
from .core.logging import get_logger, setup_logging
from .services.broadcast_helpers import close_redis_client
from .services.websockets import manager

# from .middleware.logging import LoggingMiddleware  # TODO: Create if needed


async def redis_listener(app: FastAPI):
    """
    Listens to a Redis channel and broadcasts messages to WebSocket clients.
    Reconnects automatically with exponential backoff on failure.
    """
    logger = get_logger("redis_listener")
    backoff = 1  # seconds; doubles on each failure, capped at 60

    while True:
        redis_client = None
        pubsub = None
        try:
            redis_client = redis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
            )
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("updates")
            backoff = 1  # reset on successful connect
            logger.info("redis_listener_connected")

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message.get("type") == "message":
                    logger.info(
                        "redis_message_received",
                        extra={"message_data": message["data"].decode("utf-8")},
                    )
                    await manager.broadcast(message["data"].decode("utf-8"))
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("redis_listener_cancelled")
            break  # clean shutdown — do not retry

        except Exception as e:
            logger.error(
                "redis_listener_error",
                extra={"error": str(e), "retry_in_seconds": backoff},
                exc_info=True,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

        finally:
            for resource in (pubsub, redis_client):
                if resource is not None:
                    with contextlib.suppress(Exception):
                        await resource.aclose()


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
    listener_task.cancel()
    await listener_task
    await close_redis_client()


app = FastAPI(title="Kyokki API", lifespan=lifespan)

# Add logging middleware (TODO: uncomment when middleware is created)
# app.add_middleware(LoggingMiddleware)

# CORS — origins configured via ALLOWED_ORIGINS env var (comma-separated)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
def read_root():
    return {"message": "Welcome to Kyokki API"}
