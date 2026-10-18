"""Confirm a reviewed receipt: generic products, inventory items and learned aliases (MVP-R2).

Products are generic (operator ruling 2026-09-14): SNELLMAN and ATRIA NAUDAN JAUHELIHA are
both "Ground beef". A confirmed item names an existing product (``product_id``), or a **new**
product by name. A name that already belongs to a product (a canonical or cook name) is never
joined silently: the whole confirm answers ``NameExists`` (409 ``name_exists``) listing every
such item, and the cook chooses (CL8, `docs/PRODUCT_IDENTITY_SPEC.md`). Each printed receipt
name is learned as a store alias, so the next receipt from that store arrives pre-matched.

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
from sqlalchemy.orm.attributes import flag_modified

from app.core.logging import get_logger
from app.crud.product_name import learn_product_name
from app.domain.product_names import normalize_product_name
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.schemas.receipt import (
    ConfirmedItemCreate,
    ReceiptStatus,
    ServedIdentity,
    served_identity,
)
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
from app.services.product_identity import JoinSource, decide_name
from app.services.store_chain import normalize_store_chain

logger = get_logger(__name__)

UNKNOWN_CHAIN = "unknown"

# A sane cap for a printed line, stored alongside the index so the item's sheet reads
# right even if `ocr_structured` is later re-read differently (Q26).
RECEIPT_LINE_TEXT_MAX_LENGTH = 500


class ReceiptNotFound(LookupError):
    """No receipt with that id."""


class ReceiptNotConfirmable(Exception):
    """The receipt is already confirmed or has not been read yet."""


class InvalidConfirmItem(ValueError):
    """An item cannot be resolved to a product; nothing was written."""


@dataclass(frozen=True)
class NameClash:
    """An item whose new-product name already belongs to a product (CL8)."""

    position: int
    line_id: str | None
    index: int | None
    name: str
    product_id: UUID
    product_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "line_id": self.line_id,
            "index": self.index,
            "name": self.name,
            "product_id": str(self.product_id),
            "product_name": self.product_name,
        }


class NameExists(Exception):
    """One or more items name a product that already exists; nothing was written.

    The endpoint answers 409 ``name_exists`` with every clash, so the client can ask the
    cook, for each, "use the existing product, or name this one differently?".
    """

    def __init__(self, clashes: Sequence[NameClash]):
        self.clashes = list(clashes)
        count = len(self.clashes)
        super().__init__(
            f"{count} line{'s' if count != 1 else ''} "
            f"name{'s' if count == 1 else ''} a product that already exists"
        )


@dataclass
class ConfirmResult:
    receipt: Receipt
    items_created: int = 0
    products_created: int = 0
    aliases_learned: int = 0
    inventory_items: list[tuple[InventoryItem, ProductMaster]] = field(
        default_factory=list
    )
    # The products this confirm created, for the caller to have estimated (Q19)
    created_product_ids: list[UUID] = field(default_factory=list)


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

    def line(
        self, position: int, item: ConfirmedItemCreate
    ) -> tuple[int | None, dict[str, Any]]:
        """The receipt line this item refers to, by identity where the client gave one.

        `index` is the line's raw position in `self.lines`: `items_from_structured`
        enumerates the full raw list without renumbering, so a line the model could not
        read is simply left out of what the client sees, and no index after it shifts.
        `line_id` is still preferred (H12): it survives a later re-read, where `index`
        would point at whatever line ended up at that position instead.

        Returns the line's own raw position in `self.lines` alongside it (Q26): for an
        index lookup that is `item.index` itself; for a `line_id` lookup, wherever it
        was found.
        """
        if item.line_id is not None:
            wanted = str(item.line_id)
            for raw_index, candidate in enumerate(self.lines):
                if (
                    isinstance(candidate, dict)
                    and str(candidate.get("line_id") or "") == wanted
                ):
                    if not candidate.get("name"):
                        break
                    return raw_index, candidate
            raise InvalidConfirmItem(f"Item {position}: receipt has no line {wanted}")

        if item.index is None:
            return None, {}
        line = self.lines[item.index] if item.index < len(self.lines) else None
        if not isinstance(line, dict) or not line.get("name"):
            raise InvalidConfirmItem(
                f"Item {position}: receipt has no line {item.index}"
            )
        return item.index, line

    @staticmethod
    def _name_for(item: ConfirmedItemCreate, line: dict[str, Any]) -> str | None:
        """The new product's name: typed, else the line's generic name, else printed."""
        return item.name or line.get("generic_name") or line.get("name")

    async def clashes(self, items: Sequence[ConfirmedItemCreate]) -> list[NameClash]:
        """Every item whose new-product name is already a product's key (CL8).

        Checked for all items before anything is written. A name the model taught is not
        a key (`decide_name`), so it never blocks.
        """
        found: list[NameClash] = []
        for position, item in enumerate(items):
            if item.product_id is not None:
                continue
            line_index, line = self.line(position, item)
            name = self._name_for(item, line)
            joined = await decide_name(self.db, name)
            if joined is None:
                continue
            line_id = line.get("line_id") if line else None
            found.append(
                NameClash(
                    position=position,
                    line_id=str(line_id or item.line_id or "") or None,
                    index=line_index if line_index is not None else item.index,
                    name=str(name),
                    product_id=cast(UUID, joined.product.id),
                    product_name=str(joined.product.canonical_name),
                )
            )
        return found

    async def product(
        self, position: int, item: ConfirmedItemCreate, line: dict[str, Any]
    ) -> ProductMaster:
        name = self._name_for(item, line)
        try:
            product, created = await self.resolver.resolve(
                product_id=item.product_id,
                name=name,
                category=item.category or line.get("category"),
                unit=item.unit,
                quantity=item.quantity,
                # What the model worked out about this product while reading the receipt
                piece_grams=line.get("piece_grams"),
                pack_grams=line.get("pack_grams"),
                shelf_life_days=line.get("shelf_life_days"),
                opened_shelf_life_days=line.get("opened_shelf_life_days"),
            )
        except InvalidProductRequest as exc:
            raise InvalidConfirmItem(f"Item {position}: {exc}") from exc
        if created:
            self.result.products_created += 1
            self.result.created_product_ids.append(cast(UUID, product.id))
        return product

    @staticmethod
    def _served(line: dict[str, Any]) -> ServedIdentity:
        return served_identity(line)

    @classmethod
    def _kept(cls, line: dict[str, Any], product: ProductMaster) -> bool:
        """Whether the cook kept the exact key the line was served with."""
        proposed = cls._served(line).product_id
        return proposed is not None and str(proposed) == str(product.id)

    @classmethod
    def _accepted(
        cls, line: dict[str, Any], product: ProductMaster, item: ConfirmedItemCreate
    ) -> bool:
        """Whether this item is the line's served suggestion, accepted by the cook."""
        if not item.accepted_suggestion or item.product_id is None:
            return False
        suggestion = cls._served(line).suggestion or {}
        return str(suggestion.get("product_id") or "") == str(product.id)

    @classmethod
    def _provenance(
        cls, line: dict[str, Any], product: ProductMaster, item: ConfirmedItemCreate
    ) -> tuple[str, bool]:
        """How the cook's choice relates to what was served (spec §3.4, CL8).

        Returns the alias `source` and whether it is verified memory. A kept key is
        reinforced with its own provenance; an accepted suggestion is `cook_accepted`;
        anything else - a search pick, a new product - is the cook's own word.
        """
        if cls._kept(line, product):
            served = cls._served(line)
            if served.match_source == "alias":
                return served.alias_source or "cook", served.verified
            return "name", served.verified
        if cls._accepted(line, product, item):
            return "cook_accepted", True
        return "cook", True

    @classmethod
    def _join(
        cls, line: dict[str, Any], product: ProductMaster, item: ConfirmedItemCreate
    ) -> tuple[JoinSource, str | None]:
        """`inventory_item.join_source` / `join_key` for this item (CL8 provenance)."""
        printed = normalize_receipt_name(str(line["name"])) if line.get("name") else ""
        if item.product_id is None:
            return "created", normalize_product_name(cls._name_for(item, line)) or None
        if cls._kept(line, product):
            served = cls._served(line)
            if served.match_source == "alias":
                return "alias", served.join_key or printed or None
            return "name", served.join_key or normalize_product_name(
                str(line.get("name") or "")
            ) or None
        if cls._accepted(line, product, item):
            return "accepted_suggestion", printed or None
        return "cook_pick", printed or None

    async def learn_names(
        self, line: dict[str, Any], product: ProductMaster, item: ConfirmedItemCreate
    ) -> None:
        """Record the generic name as a key for this product (spec §3.4, right column).

        It is what makes "Minced beef" hit "Ground beef" next week without the
        extraction prompt carrying the catalog.

        The name is the cook's word only when the cook acted on this line: picked or
        named the product, or typed the name. Keeping a served key or accepting a
        suggestion says nothing about the model's generic name for the line, so that is
        learned as the model's (H51, CL8): a model name is never learned as the cook's
        from an untouched suggestion.
        """
        untouched = self._kept(line, product) or self._accepted(line, product, item)
        cook_acted = item.name is not None or not untouched
        learned = item.name or line.get("generic_name")
        if learned:
            await learn_product_name(
                self.db, product, learned, "cook" if cook_acted else "model"
            )

    async def learn_alias(
        self, line: dict[str, Any], product: ProductMaster, item: ConfirmedItemCreate
    ) -> None:
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
        source, verified = self._provenance(line, product, item)

        if alias is None:
            alias = StoreProductAlias(
                product_master_id=product.id,
                store_chain=self.chain,
                receipt_name=receipt_name,
                source=source,
                confidence_score=1.0 if verified else 0.5,
                manually_verified=verified,
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
            repointed = str(row.product_master_id) != str(product.id)
            row.product_master_id = product.id
            # Never demote memory the cook stands behind: a machine mapping must not
            # overwrite a correction, and reinforcing an existing alias keeps its source.
            if verified or not row.manually_verified:
                row.source = (
                    source if repointed or not row.manually_verified else row.source
                )
                row.manually_verified = bool(row.manually_verified) or verified
                row.confidence_score = 1.0 if row.manually_verified else 0.5
            row.occurrence_count = (row.occurrence_count or 0) + 1
            row.last_seen = now
        self.aliases[receipt_name] = alias
        self.result.aliases_learned += 1

    async def add(self, position: int, item: ConfirmedItemCreate) -> None:
        line_index, line = self.line(position, item)
        product = await self.product(position, item, line)
        join_source, join_key = self._join(line, product, item)
        inventory_item = build_inventory_item(
            product,
            quantity=item.quantity,
            unit=item.unit,
            purchase_date=item.purchase_date,
            expiry_date=item.expiry_date,
            location=item.location,
            receipt_id=cast(UUID, self.receipt.id),
            join_source=join_source,
            join_key=join_key,
        )
        # Where this item came from on the receipt (Q26); NULL for an item added
        # without a line (a free line, or a product-id-only item with no `index`).
        item_row: Any = inventory_item  # Column-typed model: assign plain values
        item_row.receipt_line_index = line_index
        line_name = line.get("name") if line else None
        item_row.receipt_line_text = (
            str(line_name)[:RECEIPT_LINE_TEXT_MAX_LENGTH] if line_name else None
        )
        self.db.add(inventory_item)
        self.result.inventory_items.append((inventory_item, product))
        self.result.items_created += 1
        if line:
            await self.learn_alias(line, product, item)
            await self.learn_names(line, product, item)


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

    _mark_confirmed_non_food(confirmation, skipped)


def _mark_stocked(confirmation: "_Confirmation") -> None:
    """Record, on the receipt's own stored lines, which ones this confirm stocked.

    A hard-deleted `InventoryItem` leaves no other trace anywhere: no soft-delete
    column, no audit table, and `crud.inventory_item.delete_inventory_item` does a
    plain `db.delete` that nothing else logs. Without this mark, the audit view cannot
    tell "the cook never stocked this line" from "the cook stocked it and the item is
    gone since" - both look identical once the row is gone, and the line would read
    `skipped` either way (audit follow-up from round 2026-09-30-1). Written in the same
    transaction as the items it describes, on the receipt `confirm_receipt` already
    holds `FOR UPDATE`, so it either lands with the rest of the confirm or not at all.

    Same in-place-mutation / `flag_modified` pattern as `_mark_confirmed_non_food`.
    """
    marked = False
    for item, _product in confirmation.result.inventory_items:
        index = cast("int | None", item.receipt_line_index)
        if index is None or not (0 <= index < len(confirmation.lines)):
            continue
        line = confirmation.lines[index]
        if isinstance(line, dict) and not line.get("stocked_at_confirm"):
            line["stocked_at_confirm"] = True
            marked = True
    if marked:
        flag_modified(confirmation.receipt, "ocr_structured")


def _mark_confirmed_non_food(
    confirmation: "_Confirmation", skipped: Iterable[int]
) -> None:
    """Record, on this receipt's own stored lines, which ones were folded away as
    household *in this confirm* (Q28).

    `remember_non_food` above only teaches the printed name for *future* receipts;
    nothing recorded that this line was household on *this* one, so a never-seen
    household line read `skipped` on the audit view instead of `household`. A line
    already flagged `non_food` at extraction time needs nothing further: the audit
    checks `stocked` before `household`, so a line the cook included anyway still
    reads `stocked` regardless of this flag.

    Mutating the dicts inside `confirmation.lines` changes the very list the receipt's
    `ocr_structured` already holds (`_Confirmation.__init__` reads it, not a copy), but
    SQLAlchemy does not notice an in-place JSONB mutation on its own - `flag_modified`
    tells it to write the column back.
    """
    marked = False
    for index in skipped:
        if not (0 <= index < len(confirmation.lines)):
            continue
        line = confirmation.lines[index]
        if isinstance(line, dict) and not line.get("confirmed_non_food"):
            line["confirmed_non_food"] = True
            marked = True
    if marked:
        flag_modified(confirmation.receipt, "ocr_structured")


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
        NameExists: items name existing products by a new-product name; nothing written.
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
        # Before anything is written: a name never joins an existing product (CL8)
        clashes = await confirmation.clashes(items)
        if clashes:
            raise NameExists(clashes)
        included_indexes: set[int] = set()
        for position, item in enumerate(items):
            await confirmation.add(position, item)
            if item.index is not None:
                included_indexes.add(item.index)
        # Only lines the cook marked; an ordinary skip must not teach anything (Q1)
        await _apply_non_food(db, confirmation, non_food_indexes, included_indexes)
        _mark_stocked(confirmation)
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
    # Stock already in the kitchen that moved because this receipt replaced its product's
    # placeholder shelf life (Q19)
    for moved in confirmation.resolver.moved:
        await broadcast_inventory_update(
            inventory_item_id=moved.id,
            action="updated",
            current_quantity=moved.current_quantity,
            status=moved.status,
        )
    await broadcast_receipt_status(
        receipt_id=cast(UUID, receipt.id),
        status="confirmed",
        items_extracted=int(receipt.items_extracted or 0),
        items_matched=result.items_created,
    )
    return result
