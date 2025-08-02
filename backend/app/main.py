import asyncio
import redis.asyncio as redis
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .services.websockets import manager
from .core.config import settings

async def redis_listener(app: FastAPI):
    """
    Listens to a Redis channel and broadcasts messages to WebSocket clients.
    """
    redis_client = redis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("item_updates")
    
    print("Redis listener started. Waiting for messages...")
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                print(f"Received message from Redis: {message['data'].decode('utf-8')}")
                await manager.broadcast(message["data"].decode("utf-8"))
            await asyncio.sleep(0.1) # Short sleep to prevent high CPU usage
    except asyncio.CancelledError:
        print("Redis listener cancelled.")
    finally:
        print("Closing Redis listener.")
        await pubsub.unsubscribe("item_updates")
        await pubsub.close()
        await redis_client.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Application starting up...")
    # Start the Redis listener as a background task
    listener_task = asyncio.create_task(redis_listener(app))
    yield
    # Shutdown
    print("Application shutting down...")
    # Cancel the listener task and wait for it to finish
    listener_task.cancel()
    await listener_task

app = FastAPI(title="Fridge Logger API", lifespan=lifespan)

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
    return {"message": "Welcome to Fridge Logger API"}

