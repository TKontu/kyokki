"""Confirm a reviewed receipt: generic products, inventory items and learned aliases (MVP-R2).

Products are generic (operator ruling 2026-09-14): SNELLMAN and ATRIA NAUDAN JAUHELIHA are
both "Ground beef". A confirmed item names an existing product, or a generic name that is reused
case-insensitively or created (rules in ``services/generic_products.py``). Each printed receipt name is learned as a store alias, so the next
receipt from that store arrives pre-matched.

Everything is written in one transaction; any invalid item rolls the whole confirm back.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.schemas.receipt import ConfirmedItemCreate, ReceiptStatus
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_receipt_status,
)
from app.services.generic_products import (
    InvalidProductRequest,
    ProductResolver,
    build_inventory_item,
)
from app.services.matching_service import normalize_receipt_name
from app.services.non_food import forget_non_food, remember_non_food
from app.services.product_names import learn_product_name
from app.services.store_chain import normalize_store_chain

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
        self.resolver = ProductResolver(db)
        self.aliases: dict[str, StoreProductAlias] = {}

    def line(self, position: int, item: ConfirmedItemCreate) -> dict[str, Any]:
        """The receipt line this item refers to, by identity where the client gave one.

        `index` is a position among *readable* lines, so an unreadable line anywhere
        shifts every index after it and the wrong printed name gets learned as an alias.
        `line_id` does not move (H12); `index` stays for receipts read before it.
        """
        if item.line_id is not None:
            wanted = str(item.line_id)
            for candidate in self.lines:
                if (
                    isinstance(candidate, dict)
                    and str(candidate.get("line_id") or "") == wanted
                ):
                    if not candidate.get("name"):
                        break
                    return candidate
            raise InvalidConfirmItem(f"Item {position}: receipt has no line {wanted}")

        if item.index is None:
            return {}
        line = self.lines[item.index] if item.index < len(self.lines) else None
        if not isinstance(line, dict) or not line.get("name"):
            raise InvalidConfirmItem(
                f"Item {position}: receipt has no line {item.index}"
            )
        return line

    async def product(
        self, position: int, item: ConfirmedItemCreate, line: dict[str, Any]
    ) -> ProductMaster:
        try:
            product, created = await self.resolver.resolve(
                product_id=item.product_id,
                name=item.name or line.get("generic_name") or line.get("name"),
                category=item.category or line.get("category"),
                unit=item.unit,
                quantity=item.quantity,
                # What the model worked out about this product while reading the receipt
                piece_grams=line.get("piece_grams"),
                shelf_life_days=line.get("shelf_life_days"),
                opened_shelf_life_days=line.get("opened_shelf_life_days"),
            )
        except InvalidProductRequest as exc:
            raise InvalidConfirmItem(f"Item {position}: {exc}") from exc
        if created:
            self.result.products_created += 1

        # The generic name becomes a key, so the same thing under another brand resolves
        # without the model next week (spec §3.4). `cook` when the cook typed the name
        # here, `model` when it came from the read line. Only the cook's own action
        # produces verified memory, and the full precedence table lands in H14.
        learned_name = item.name or line.get("generic_name")
        if learned_name:
            await learn_product_name(
                self.db, product, learned_name, "cook" if item.name else "model"
            )
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
        inventory_item = build_inventory_item(
            product,
            quantity=item.quantity,
            unit=item.unit,
            purchase_date=item.purchase_date,
            expiry_date=item.expiry_date,
            location=item.location,
            receipt_id=cast(UUID, self.receipt.id),
        )
        self.db.add(inventory_item)
        self.result.inventory_items.append((inventory_item, product))
        self.result.items_created += 1
        if line:
            await self.learn_alias(line, product)


def _printed_names(confirmation: "_Confirmation", indexes: Iterable[int]) -> list[str]:
    return [
        str(confirmation.lines[i]["name"])
        for i in indexes
        if 0 <= i < len(confirmation.lines) and confirmation.lines[i].get("name")
    ]


async def _apply_non_food(
    db: AsyncSession,
    confirmation: "_Confirmation",
    indexes: Sequence[int],
    included_indexes: set[int],
) -> None:
    """Remember the lines the cook folded away, and forget the ones they kept (Q1).

    A line could previously be confirmed *and* listed as non-food in the same
    request - nothing cross-checked the two - so the cook correcting a wrong
    household guess taught the alias and wrote the non-food memory at once, and
    the same line was hidden again on the next receipt.
    """
    skipped = [i for i in indexes if i not in included_indexes]
    corrected = [i for i in indexes if i in included_indexes]

    remembered = _printed_names(confirmation, skipped)
    if remembered:
        await remember_non_food(db, confirmation.chain, remembered)

    forgotten = _printed_names(confirmation, corrected)
    if forgotten:
        await forget_non_food(db, confirmation.chain, forgotten)


async def confirm_receipt(
    db: AsyncSession,
    receipt_id: UUID,
    items: Sequence[ConfirmedItemCreate],
    non_food_indexes: Sequence[int] = (),
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
        included_indexes: set[int] = set()
        for position, item in enumerate(items):
            await confirmation.add(position, item)
            if item.index is not None:
                included_indexes.add(item.index)
        # Only lines the cook marked; an ordinary skip must not teach anything (Q1)
        await _apply_non_food(db, confirmation, non_food_indexes, included_indexes)
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
