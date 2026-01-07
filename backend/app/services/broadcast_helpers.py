"""Helper functions for broadcasting real-time updates via Redis."""
import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
from typing import Dict, Any, Literal
import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Redis client for publishing (separate from listener)
_redis_client = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client for publishing."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
        )
    return _redis_client


def _serialize_value(value: Any) -> Any:
    """Serialize values for JSON encoding.

    Args:
        value: Value to serialize.

    Returns:
        JSON-serializable value.
    """
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_message(
    message_type: Literal["receipt_status", "inventory_update"],
    entity_id: UUID,
    data: Dict[str, Any]
) -> Dict[str, Any]:
    """Build standardized message structure.

    Args:
        message_type: Type of message (receipt_status, inventory_update).
        entity_id: UUID of the entity (receipt or inventory item).
        data: Type-specific payload data.

    Returns:
        Standardized message dictionary.
    """
    return {
        "type": message_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entity_id": str(entity_id),
        "data": {k: _serialize_value(v) for k, v in data.items()}
    }


async def publish_message(message: Dict[str, Any]) -> None:
    """Publish message to Redis updates channel.

    Args:
        message: Message dictionary to publish.
    """
    try:
        redis_client = await get_redis_client()
        message_json = json.dumps(message)
        await redis_client.publish("updates", message_json)

        logger.info(
            "message_published",
            extra={
                "message_type": message.get("type"),
                "entity_id": message.get("entity_id")
            }
        )
    except Exception as e:
        logger.error(
            "message_publish_failed",
            extra={
                "error": str(e),
                "message_type": message.get("type")
            },
            exc_info=True
        )


async def broadcast_receipt_status(
    receipt_id: UUID,
    status: Literal["processing", "completed", "failed", "confirmed"],
    items_extracted: int = 0,
    items_matched: int = 0,
    error: str | None = None
) -> None:
    """Broadcast receipt processing status update.

    Args:
        receipt_id: Receipt UUID.
        status: Processing status.
        items_extracted: Number of items extracted from receipt.
        items_matched: Number of items matched to products.
        error: Error message if status is "failed".
    """
    message = _build_message(
        message_type="receipt_status",
        entity_id=receipt_id,
        data={
            "receipt_id": receipt_id,
            "status": status,
            "items_extracted": items_extracted,
            "items_matched": items_matched,
            "error": error
        }
    )
    await publish_message(message)


async def broadcast_inventory_update(
    inventory_item_id: UUID,
    action: Literal["created", "updated", "consumed", "deleted"],
    current_quantity: Decimal | None = None,
    status: str | None = None,
    product_name: str | None = None
) -> None:
    """Broadcast inventory item update.

    Args:
        inventory_item_id: Inventory item UUID.
        action: Type of action performed.
        current_quantity: Current quantity (if applicable).
        status: Item status (if applicable).
        product_name: Product name for display purposes.
    """
    message = _build_message(
        message_type="inventory_update",
        entity_id=inventory_item_id,
        data={
            "inventory_item_id": inventory_item_id,
            "action": action,
            "current_quantity": current_quantity,
            "status": status,
            "product_name": product_name
        }
    )
    await publish_message(message)
