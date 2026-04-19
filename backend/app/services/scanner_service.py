"""Scanner service — Redis mode management, station tracking, and scan processing."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import inventory_item as crud_inventory
from app.crud import product_master as crud_product
from app.schemas.inventory_item import InventoryItemCreate
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_scanner_action,
    get_redis_client,
)
from app.services.off_service import (
    OffApiError,
    OffProductNotFoundError,
    enrich_product_from_off,
    fetch_product_from_off,
)

GLOBAL_MODE_KEY = "scanner:mode:global"
DEFAULT_MODE = "add"
STATION_ONLINE_TTL = 300  # 5 minutes


def _mode_key(station_id: str) -> str:
    return f"scanner:mode:{station_id}"


def _station_last_scan_key(station_id: str) -> str:
    return f"scanner:station:{station_id}:last_scan"


def _station_scan_count_key(station_id: str) -> str:
    return f"scanner:station:{station_id}:scan_count"


def _station_online_key(station_id: str) -> str:
    return f"scanner:station:{station_id}:online"


async def get_mode(station_id: str | None) -> tuple[str, bool]:
    """Get effective scanning mode and whether it's the global fallback.

    Checks station-specific key first, falls back to global, then DEFAULT_MODE.

    Args:
        station_id: Optional station ID to check.

    Returns:
        Tuple of (mode, is_global).
    """
    redis = await get_redis_client()

    if station_id:
        station_mode = await redis.get(_mode_key(station_id))
        if station_mode:
            return station_mode.decode(), False

    global_mode = await redis.get(GLOBAL_MODE_KEY)
    if global_mode:
        return global_mode.decode(), True

    return DEFAULT_MODE, True


async def set_mode(mode: str, station_id: str | None) -> None:
    """Set scanning mode in Redis.

    Args:
        mode: Mode to set (add, consume, lookup).
        station_id: If provided, sets per-station mode; else sets global.
    """
    redis = await get_redis_client()
    key = _mode_key(station_id) if station_id else GLOBAL_MODE_KEY
    await redis.set(key, mode)


async def update_station_activity(station_id: str, mode: str) -> None:
    """Record scan activity for a station.

    Updates last_scan timestamp, increments scan_count, and marks station online
    with a TTL of STATION_ONLINE_TTL seconds.

    Args:
        station_id: Station ID to update.
        mode: Current mode (stored alongside station info).
    """
    redis = await get_redis_client()
    now = datetime.now(UTC).isoformat()

    await redis.set(_station_last_scan_key(station_id), now)
    await redis.incr(_station_scan_count_key(station_id))
    await redis.set(_station_online_key(station_id), "true", ex=STATION_ONLINE_TTL)

    # Also ensure station mode is set (so stations endpoint can read it)
    existing = await redis.get(_mode_key(station_id))
    if not existing:
        await redis.set(_mode_key(station_id), mode)


async def get_all_stations() -> list[dict]:
    """Return all known stations with their current state.

    Discovers stations by scanning for online keys, then reads their metadata.

    Returns:
        List of station info dicts.
    """
    redis = await get_redis_client()

    # Find all station online keys
    online_keys = await redis.keys("scanner:station:*:online")
    stations = []

    for key in online_keys:
        # Extract station_id from key pattern "scanner:station:{id}:online"
        key_str = key.decode() if isinstance(key, bytes) else key
        parts = key_str.split(":")
        if len(parts) != 4:
            continue
        station_id = parts[2]

        # Read station metadata
        last_scan_raw = await redis.get(_station_last_scan_key(station_id))
        scan_count_raw = await redis.get(_station_scan_count_key(station_id))
        online_raw = await redis.get(_station_online_key(station_id))
        mode_raw = await redis.get(_mode_key(station_id))

        stations.append(
            {
                "station_id": station_id,
                "mode": mode_raw.decode() if mode_raw else DEFAULT_MODE,
                "last_scan": last_scan_raw.decode() if last_scan_raw else None,
                "scan_count": int(scan_count_raw) if scan_count_raw else 0,
                "online": online_raw is not None,
            }
        )

    return stations


async def process_scan(
    db: AsyncSession,
    barcode: str,
    mode: str,
    station_id: str | None,
    quantity: Decimal,
) -> dict:
    """Process a barcode scan and perform the configured action.

    Args:
        db: Database session.
        barcode: Scanned barcode string.
        mode: Scanning mode (add, consume, lookup).
        station_id: Optional station ID for activity tracking.
        quantity: Quantity to add or consume.

    Returns:
        Response dict with success, action, product, inventory_item, message.

    Raises:
        ValueError: If product not found (404 case) or no active inventory (consume).
    """
    if station_id:
        await update_station_activity(station_id, mode)

    if mode == "consume":
        return await _handle_consume(db, barcode, station_id, quantity)
    elif mode == "lookup":
        return await _handle_lookup(db, barcode)
    else:
        return await _handle_add(db, barcode, station_id, quantity)


async def _handle_add(
    db: AsyncSession,
    barcode: str,
    station_id: str | None,
    quantity: Decimal,
) -> dict:
    """Add mode: find or create product, then create inventory item."""
    product = await crud_product.get_product_by_barcode(db, barcode)
    created_product = False

    if not product:
        enriched = await enrich_product_from_off(barcode)
        product, created_product = await crud_product.enrich_product_from_off_data(
            db, enriched
        )

    action = "product_created_and_added" if created_product else "inventory_added"

    # Build inventory item with product defaults
    shelf_life = product.default_shelf_life_days or 365
    expiry = datetime.now(UTC).date() + timedelta(days=shelf_life)

    # Map storage_type to location
    location_map = {
        "refrigerator": "main_fridge",
        "freezer": "freezer",
        "pantry": "pantry",
    }
    location = location_map.get(product.storage_type, "main_fridge")

    item_quantity = (
        product.default_quantity if product.default_quantity is not None else quantity
    )

    inventory_create = InventoryItemCreate(
        product_master_id=product.id,
        initial_quantity=item_quantity,
        current_quantity=item_quantity,
        unit=product.default_unit,
        expiry_date=expiry,
        location=location,
        purchase_date=datetime.now(UTC).date(),
    )
    inv_item = await crud_inventory.create_inventory_item(db, inventory_create)

    await broadcast_scanner_action(
        action=action,
        barcode=barcode,
        product_name=product.canonical_name,
        station_id=station_id,
        mode="add",
        quantity=inv_item.current_quantity,
        unit=inv_item.unit,
        entity_id=inv_item.id,
    )
    await broadcast_inventory_update(
        inventory_item_id=inv_item.id,
        action="created",
        current_quantity=inv_item.current_quantity,
        status=inv_item.status,
        product_name=product.canonical_name,
    )

    return {
        "success": True,
        "action": action,
        "product": {
            "id": str(product.id),
            "canonical_name": product.canonical_name,
            "category": product.category,
            "storage_type": product.storage_type,
        },
        "inventory_item": {
            "id": str(inv_item.id),
            "initial_quantity": str(inv_item.initial_quantity),
            "current_quantity": str(inv_item.current_quantity),
            "unit": inv_item.unit,
        },
        "message": f"Added {product.canonical_name} to inventory",
    }


async def _handle_consume(
    db: AsyncSession,
    barcode: str,
    station_id: str | None,
    quantity: Decimal,
) -> dict:
    """Consume mode: find product, consume from oldest active inventory item."""
    product = await crud_product.get_product_by_barcode(db, barcode)
    if not product:
        raise ValueError(f"Product with barcode {barcode} not found")

    active_items = await crud_inventory.get_active_items_by_product(db, product.id)
    if not active_items:
        raise ValueError(
            f"No active inventory for {product.canonical_name}. Add it first."
        )

    # Consume from oldest (first due to expiry ASC ordering)
    inv_item = active_items[0]
    consume_qty = min(quantity, inv_item.current_quantity)
    updated = await crud_inventory.consume_inventory_item(db, inv_item.id, consume_qty)

    await broadcast_scanner_action(
        action="inventory_consumed",
        barcode=barcode,
        product_name=product.canonical_name,
        station_id=station_id,
        mode="consume",
        quantity=consume_qty,
        unit=inv_item.unit,
        entity_id=inv_item.id,
    )
    await broadcast_inventory_update(
        inventory_item_id=inv_item.id,
        action="consumed",
        current_quantity=updated.current_quantity if updated else None,
        status=updated.status if updated else None,
        product_name=product.canonical_name,
    )

    return {
        "success": True,
        "action": "inventory_consumed",
        "product": {
            "id": str(product.id),
            "canonical_name": product.canonical_name,
            "category": product.category,
            "storage_type": product.storage_type,
        },
        "inventory_item": {
            "id": str(inv_item.id),
            "current_quantity": str(updated.current_quantity) if updated else "0",
            "status": updated.status if updated else "empty",
            "unit": inv_item.unit,
        },
        "message": f"Consumed {consume_qty} {inv_item.unit} of {product.canonical_name}",
    }


async def _handle_lookup(db: AsyncSession, barcode: str) -> dict:
    """Lookup mode: return product info without modifying inventory."""
    product = await crud_product.get_product_by_barcode(db, barcode)

    if product:
        return {
            "success": True,
            "action": "lookup",
            "product": {
                "id": str(product.id),
                "canonical_name": product.canonical_name,
                "category": product.category,
                "storage_type": product.storage_type,
            },
            "inventory_item": None,
            "message": f"Found {product.canonical_name} in local database",
        }

    # Try OFF (read-only, no DB writes)
    try:
        off_data = await fetch_product_from_off(barcode)
        product_data = off_data.get("product", {})
        name = product_data.get("product_name") or "Unknown Product"
        return {
            "success": True,
            "action": "lookup",
            "product": {
                "id": None,
                "canonical_name": name,
                "category": None,
                "storage_type": None,
                "off_data": product_data,
            },
            "inventory_item": None,
            "message": f"Found {name} in Open Food Facts",
        }
    except OffProductNotFoundError as e:
        raise ValueError(f"Product with barcode {barcode} not found anywhere") from e
    except OffApiError as e:
        raise ValueError(
            f"Product with barcode {barcode} not found locally and OFF is unavailable"
        ) from e
