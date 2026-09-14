"""Confirm a reviewed receipt: generic products, inventory items and learned aliases (MVP-R2).

Products are generic (operator ruling 2026-09-14): SNELLMAN and ATRIA NAUDAN JAUHELIHA are
both "Ground beef". A confirmed item names an existing product, or a generic name that is reused
case-insensitively or created. Each printed receipt name is learned as a store alias, so the next
receipt from that store arrives pre-matched.

Everything is written in one transaction; any invalid item rolls the whole confirm back.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud.category import get_category
from app.models.category import Category
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.schemas.receipt import ConfirmedItemCreate, ReceiptStatus
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_receipt_status,
)
from app.services.matching_service import normalize_receipt_name
from app.services.storage import location_for_storage, storage_type_for_category
from app.services.store_chain import normalize_store_chain
from app.services.units import unit_type_for

logger = get_logger(__name__)

UNKNOWN_CHAIN = "unknown"


class ReceiptNotFound(LookupError):
    """No receipt with that id."""


class ReceiptNotConfirmable(Exception):
    """The receipt is already confirmed or has not been read yet."""


class InvalidConfirmItem(ValueError):
    """An item cannot be resolved to a product; nothing was written."""


@dataclass
class ConfirmResult:
    receipt: Receipt
    items_created: int = 0
    products_created: int = 0
    aliases_learned: int = 0
    inventory_items: list[tuple[InventoryItem, ProductMaster]] = field(
        default_factory=list
    )


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


class _Confirmation:
    def __init__(self, db: AsyncSession, receipt: Receipt):
        self.db = db
        self.receipt = receipt
        self.result = ConfirmResult(receipt=receipt)
        structured: dict[str, Any] = (
            receipt.ocr_structured if isinstance(receipt.ocr_structured, dict) else {}
        )
        lines = structured.get("lines")
        self.lines: list[Any] = lines if isinstance(lines, list) else []
        self.chain = (
            normalize_store_chain(
                str(receipt.store_chain) if receipt.store_chain else None
            )
            or UNKNOWN_CHAIN
        )
        self.products_by_name: dict[str, ProductMaster] = {}
        self.categories: dict[str, Category | None] = {}
        self.aliases: dict[str, StoreProductAlias] = {}

    def line(self, position: int, item: ConfirmedItemCreate) -> dict[str, Any]:
        if item.index is None:
            return {}
        line = self.lines[item.index] if item.index < len(self.lines) else None
        if not isinstance(line, dict) or not line.get("name"):
            raise InvalidConfirmItem(
                f"Item {position}: receipt has no line {item.index}"
            )
        return line

    async def category(self, category_id: str) -> Category | None:
        if category_id not in self.categories:
            self.categories[category_id] = await get_category(self.db, category_id)
        return self.categories[category_id]

    async def product(
        self, position: int, item: ConfirmedItemCreate, line: dict[str, Any]
    ) -> ProductMaster:
        if item.product_id is not None:
            product = await self.db.get(ProductMaster, item.product_id)
            if product is None:
                raise InvalidConfirmItem(
                    f"Item {position}: product '{item.product_id}' not found"
                )
            return product

        name = " ".join(
            (item.name or line.get("generic_name") or line.get("name") or "").split()
        )
        if not name:
            raise InvalidConfirmItem(f"Item {position}: no product name")
        key = _name_key(name)
        if key in self.products_by_name:
            return self.products_by_name[key]

        existing = (
            (
                await self.db.execute(
                    select(ProductMaster)
                    .where(func.lower(ProductMaster.canonical_name) == name.lower())
                    .order_by(ProductMaster.created_at)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if existing is not None:
            self.products_by_name[key] = existing
            return existing

        category_id = item.category or line.get("category")
        if not category_id:
            raise InvalidConfirmItem(f"Category required for new product '{name}'")
        category = await self.category(str(category_id))
        if category is None:
            raise InvalidConfirmItem(
                f"Unknown category '{category_id}' for new product '{name}'"
            )

        product = ProductMaster(
            canonical_name=name,
            category=category.id,
            storage_type=storage_type_for_category(str(category.id)),
            default_shelf_life_days=category.default_shelf_life_days,
            unit_type=unit_type_for(item.unit),
            default_unit=item.unit,
            default_quantity=item.quantity,
        )
        self.db.add(product)
        await self.db.flush()
        self.products_by_name[key] = product
        self.result.products_created += 1
        return product

    async def learn_alias(self, line: dict[str, Any], product: ProductMaster) -> None:
        receipt_name = normalize_receipt_name(str(line["name"]))
        if not receipt_name:
            return
        alias = self.aliases.get(receipt_name)
        if alias is None:
            alias = (
                (
                    await self.db.execute(
                        select(StoreProductAlias).where(
                            StoreProductAlias.store_chain == self.chain,
                            StoreProductAlias.receipt_name == receipt_name,
                        )
                    )
                )
                .scalars()
                .first()
            )
        now = datetime.now(UTC)
        if alias is None:
            alias = StoreProductAlias(
                product_master_id=product.id,
                store_chain=self.chain,
                receipt_name=receipt_name,
                confidence_score=1.0,
                manually_verified=True,
                occurrence_count=1,
                last_seen=now,
            )
            self.db.add(alias)
        elif receipt_name in self.aliases:
            # The same printed name twice on one receipt: one alias, pointing at the last choice
            alias.product_master_id = product.id
            return
        else:
            row: Any = alias  # Column-typed model: assign plain values
            row.product_master_id = product.id
            row.confidence_score = 1.0
            row.manually_verified = True
            row.occurrence_count = (row.occurrence_count or 0) + 1
            row.last_seen = now
        self.aliases[receipt_name] = alias
        self.result.aliases_learned += 1

    async def add(self, position: int, item: ConfirmedItemCreate) -> None:
        line = self.line(position, item)
        product = await self.product(position, item, line)
        if item.expiry_date is not None:
            expiry, source = item.expiry_date, "manual"
        else:
            expiry = item.purchase_date + timedelta(
                days=int(product.default_shelf_life_days)
            )
            source = "calculated"
        inventory_item = InventoryItem(
            product_master_id=product.id,
            receipt_id=self.receipt.id,
            initial_quantity=item.quantity,
            current_quantity=item.quantity,
            unit=item.unit,
            status="sealed",
            purchase_date=item.purchase_date,
            expiry_date=expiry,
            expiry_source=source,
            location=item.location or location_for_storage(str(product.storage_type)),
        )
        self.db.add(inventory_item)
        self.result.inventory_items.append((inventory_item, product))
        self.result.items_created += 1
        if line:
            await self.learn_alias(line, product)


async def confirm_receipt(
    db: AsyncSession, receipt_id: UUID, items: Sequence[ConfirmedItemCreate]
) -> ConfirmResult:
    """Write products, inventory and aliases for the reviewed items, then mark it confirmed.

    Raises:
        ReceiptNotFound: no such receipt.
        ReceiptNotConfirmable: already confirmed, or not ``completed``.
        InvalidConfirmItem: an item cannot be resolved; the transaction is rolled back.
    """
    try:
        # Row lock: two confirms of one receipt cannot both pass the status check
        receipt = (
            await db.execute(
                select(Receipt).where(Receipt.id == receipt_id).with_for_update()
            )
        ).scalar_one_or_none()
        if receipt is None:
            raise ReceiptNotFound(f"Receipt '{receipt_id}' not found")
        if receipt.processing_status == ReceiptStatus.CONFIRMED:
            raise ReceiptNotConfirmable("Receipt already confirmed")
        if receipt.processing_status != ReceiptStatus.COMPLETED:
            raise ReceiptNotConfirmable(
                f"Receipt is not ready to confirm (status {receipt.processing_status})"
            )

        confirmation = _Confirmation(db, receipt)
        for position, item in enumerate(items):
            await confirmation.add(position, item)
        receipt_row: Any = receipt
        receipt_row.processing_status = ReceiptStatus.CONFIRMED
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    result = confirmation.result
    logger.info(
        "Receipt confirmed",
        extra={
            "receipt_id": str(receipt_id),
            "items_created": result.items_created,
            "products_created": result.products_created,
            "aliases_learned": result.aliases_learned,
        },
    )
    for inventory_item, product in result.inventory_items:
        await broadcast_inventory_update(
            inventory_item_id=cast(UUID, inventory_item.id),
            action="created",
            current_quantity=cast(Decimal, inventory_item.current_quantity),
            status="sealed",
            product_name=str(product.canonical_name),
        )
    await broadcast_receipt_status(
        receipt_id=cast(UUID, receipt.id),
        status="confirmed",
        items_extracted=int(receipt.items_extracted or 0),
        items_matched=result.items_created,
    )
    return result
