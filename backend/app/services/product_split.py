"""Undoing a wrong join: move items off a product, and move them back (CL8 L2).

`docs/PRODUCT_IDENTITY_SPEC.md`, "Undoing a wrong join: split". An item reads its name,
icon, shelf life and display names through its product, so a stew joined to the rice-pie
product could not be told apart from the pies: renaming one renamed both, and a date typed on
the stew taught the pies. A split moves the chosen items - with their history - to another
product, in one transaction:

1. the items move, and their `consumption_log` rows follow (run-out and undo read those);
2. with `move_keys`, the printed-name aliases (per chain) of the moved receipt lines point at
   the target as the cook's word, and the names the model taught from those lines' generic
   names are forgotten from the source - so the next receipt goes to the target. The source's
   canonical name never moves;
3. both products re-learn their shelf life from the cook's dates they now hold, and their
   calculated expiries are recomputed;
4. a new target is created the way quick add creates one (`ProductResolver`), and the caller
   schedules its background pipeline (estimates, icon, emoji, display name) after commit;
5. everything changed is recorded in `product_reassignment`, with the previous values, so
   `undo_split` can replay it backwards exactly.

Display names, emoji, icon, minimum stock and shopping rows stay with the source.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.crud import product_reassignment as crud_reassignment
from app.crud.category import get_category
from app.crud.inventory_item import INACTIVE_STATUSES
from app.crud.product_master import MovedInventoryItem, references_to_product
from app.crud.product_name import product_for_name
from app.domain.product_names import normalize_product_name
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.receipt import Receipt
from app.models.store_product_alias import StoreProductAlias
from app.services import min_stock
from app.services.broadcast_helpers import (
    broadcast_inventory_update,
    broadcast_product_update,
)
from app.services.expiry_recompute import recompute_expiry_for_product
from app.services.generic_products import ProductResolver, tidy_name
from app.services.matching_service import normalize_receipt_name
from app.services.receipt_confirm import UNKNOWN_CHAIN
from app.services.shelf_life_learning import (
    count_observations,
    learn_shelf_life,
    lock_product,
)
from app.services.store_chain import normalize_store_chain

logger = get_logger(__name__)

MANUAL_KEY = "manual"


# --- Errors -----------------------------------------------------------------------------


class SplitError(Exception):
    """A split or undo refused; nothing was written."""


class UnknownProduct(SplitError):
    """The product, or the existing target, does not exist (404)."""

    def __init__(self, product_id: UUID) -> None:
        super().__init__(f"Product with ID '{product_id}' not found")
        self.product_id = product_id


class InvalidSplit(SplitError):
    """The request cannot be carried out as given (400 `invalid`)."""


class NameExists(SplitError):
    """The new product's name already means a product (409 `name_exists`)."""

    def __init__(self, product_id: UUID, name: str) -> None:
        super().__init__(f"'{name}' is already a product")
        self.product_id = product_id
        self.name = name


class UnknownReassignment(SplitError):
    """No such split record (404)."""

    def __init__(self, reassignment_id: UUID) -> None:
        super().__init__(f"Reassignment with ID '{reassignment_id}' not found")
        self.reassignment_id = reassignment_id


class StaleReassignment(SplitError):
    """Already undone, or a moved item has changed product since (409 `stale`)."""


# --- Results ----------------------------------------------------------------------------


@dataclass(frozen=True)
class NewProduct:
    name: str
    category: str


@dataclass(frozen=True)
class MovedKey:
    kind: str  # "alias" | "name"
    value: str
    store_chain: str | None = None


@dataclass(frozen=True)
class SourceShelfLife:
    days: int
    source: str
    observations_left: int


@dataclass
class SplitResult:
    reassignment_id: UUID
    source: ProductMaster
    target: ProductMaster
    target_created: bool
    moved_item_ids: list[UUID]
    moved_keys: list[MovedKey]
    source_shelf_life: SourceShelfLife


@dataclass(frozen=True)
class UndoResult:
    reassignment_id: UUID
    restored_item_ids: list[UUID]


@dataclass
class SourceGroup:
    key: str
    label: str
    store_chain: str | None
    kind: str  # "receipt" | "manual"
    item_ids: list[UUID] = field(default_factory=list)
    active_count: int = 0
    total_count: int = 0
    first_seen: date | None = None
    last_seen: date | None = None


# --- Receipt lines ----------------------------------------------------------------------


def _chain(receipt: Receipt) -> str:
    """The receipt's chain key, as confirm scoped its aliases."""
    raw = str(receipt.store_chain) if receipt.store_chain else None
    return normalize_store_chain(raw) or UNKNOWN_CHAIN


def _line(receipt: Receipt | None, index: Any) -> dict[str, Any]:
    """The stored receipt line at the item's raw position, or an empty dict."""
    if receipt is None or index is None:
        return {}
    structured = receipt.ocr_structured
    lines = structured.get("lines") if isinstance(structured, dict) else None
    if not isinstance(lines, list) or not 0 <= int(index) < len(lines):
        return {}
    line = lines[int(index)]
    return line if isinstance(line, dict) else {}


def _printed_key(item: InventoryItem, receipt: Receipt | None) -> str:
    """The item's printed receipt name as an alias key, or "" without one."""
    if receipt is None:
        return ""
    row: Any = item
    printed = row.receipt_line_text or _line(receipt, row.receipt_line_index).get(
        "name"
    )
    return normalize_receipt_name(str(printed)) if printed else ""


async def _receipts(
    db: AsyncSession, items: Sequence[InventoryItem]
) -> dict[Any, Receipt]:
    ids = {item.receipt_id for item in items if item.receipt_id is not None}
    if not ids:
        return {}
    rows = (await db.execute(select(Receipt).where(Receipt.id.in_(ids)))).scalars()
    return {receipt.id: receipt for receipt in rows}


# --- Sources ----------------------------------------------------------------------------


async def product_sources(db: AsyncSession, product_id: UUID) -> list[SourceGroup]:
    """This product's items grouped by where they came from, newest group first.

    A receipt item's group is (its receipt's chain, its normalised printed name); every item
    without a receipt line is in the one `manual` group. Read-only.

    Raises:
        UnknownProduct: No such product.
    """
    if await crud_product.get_product(db, product_id) is None:
        raise UnknownProduct(product_id)

    rows = (
        await db.execute(
            select(InventoryItem, Receipt)
            .outerjoin(Receipt, InventoryItem.receipt_id == Receipt.id)
            .where(InventoryItem.product_master_id == product_id)
            .order_by(
                InventoryItem.purchase_date,
                InventoryItem.created_at,
                InventoryItem.id,
            )
        )
    ).all()

    groups: dict[str, SourceGroup] = {}
    for item, receipt in rows:
        printed = _printed_key(item, receipt)
        if printed:
            chain = _chain(receipt)
            key = f"line:{chain}:{printed.lower()}"
            group = groups.setdefault(
                key,
                SourceGroup(key=key, label=printed, store_chain=chain, kind="receipt"),
            )
        else:
            group = groups.setdefault(
                MANUAL_KEY,
                SourceGroup(key=MANUAL_KEY, label="", store_chain=None, kind="manual"),
            )
        row: Any = item
        group.total_count += 1
        if str(row.status) not in INACTIVE_STATUSES:
            group.active_count += 1
            group.item_ids.append(row.id)
        bought = row.purchase_date
        if bought is not None:
            if group.first_seen is None or bought < group.first_seen:
                group.first_seen = bought
            if group.last_seen is None or bought > group.last_seen:
                group.last_seen = bought

    return sorted(
        groups.values(),
        key=lambda group: (
            group.last_seen is not None,
            group.last_seen or date.min,
        ),
        reverse=True,
    )


# --- Split ------------------------------------------------------------------------------


def _shelf_life(product: ProductMaster) -> dict[str, Any]:
    return {
        "days": int(product.default_shelf_life_days),
        "source": str(product.shelf_life_source),
    }


async def _move_keys(
    db: AsyncSession,
    source: ProductMaster,
    target: ProductMaster,
    items: Sequence[InventoryItem],
    receipts: dict[Any, Receipt],
    record: dict[str, Any],
) -> list[MovedKey]:
    """Point the moved lines' keys at the target; record what each was before."""
    pairs: dict[tuple[str, str], None] = {}
    generics: set[str] = set()
    for item in items:
        receipt = receipts.get(item.receipt_id)
        if receipt is None:
            continue
        printed = _printed_key(item, receipt)
        if printed:
            pairs[(_chain(receipt), printed)] = None
        generic = normalize_product_name(
            _line(receipt, cast(Any, item).receipt_line_index).get("generic_name")
        )
        if generic:
            generics.add(generic)

    moved: list[MovedKey] = []
    for chain, printed in pairs:
        alias: Any = (
            (
                await db.execute(
                    select(StoreProductAlias).where(
                        StoreProductAlias.store_chain == chain,
                        StoreProductAlias.receipt_name == printed,
                    )
                )
            )
            .scalars()
            .first()
        )
        if alias is None:
            # No key yet for this printed name at this chain (an older confirm, or one
            # forgotten since): the cook has just said what it is, so it becomes one.
            alias = StoreProductAlias(
                product_master_id=target.id,
                store_chain=chain,
                receipt_name=printed,
                source="cook",
                manually_verified=True,
                confidence_score=1.0,
                occurrence_count=1,
            )
            db.add(alias)
            await db.flush()
            record["aliases"].append({"id": str(alias.id), "created": True})
        else:
            record["aliases"].append(
                {
                    "id": str(alias.id),
                    "created": False,
                    "previous": {
                        "product_master_id": str(alias.product_master_id),
                        "source": str(alias.source),
                        "manually_verified": bool(alias.manually_verified),
                        "confidence_score": float(alias.confidence_score or 0.0),
                    },
                }
            )
            alias.product_master_id = target.id
            alias.source = "cook"
            alias.manually_verified = True
            alias.confidence_score = 1.0
        moved.append(MovedKey(kind="alias", value=printed, store_chain=chain))

    if generics:
        taught = (
            (
                await db.execute(
                    select(ProductName)
                    .where(ProductName.product_master_id == source.id)
                    .where(ProductName.source == "model")
                    .where(ProductName.name.in_(sorted(generics)))
                    .order_by(ProductName.name)
                )
            )
            .scalars()
            .all()
        )
        for name in taught:
            record["names"].append(
                {
                    "name": str(name.name),
                    "source": str(name.source),
                    "product_master_id": str(name.product_master_id),
                }
            )
            moved.append(MovedKey(kind="name", value=str(name.name)))
            await db.delete(name)
    await db.flush()
    return moved


async def _validate_target(
    db: AsyncSession,
    source_id: UUID,
    target_product_id: UUID | None,
    new: NewProduct | None,
) -> tuple[ProductMaster | None, str]:
    """The existing target, or None and the tidied new name."""
    if (target_product_id is None) == (new is None):
        raise InvalidSplit("Name exactly one target: an existing product or a new one")
    if target_product_id is not None:
        if target_product_id == source_id:
            raise InvalidSplit("The target is the product the items are already on")
        target = await crud_product.get_product(db, target_product_id)
        if target is None:
            raise UnknownProduct(target_product_id)
        return target, ""

    assert new is not None
    name = tidy_name(new.name)
    if not name:
        raise InvalidSplit("The new product needs a name")
    if await get_category(db, new.category) is None:
        raise InvalidSplit(f"Unknown category '{new.category}'")
    return None, name


async def split_items(
    db: AsyncSession,
    product_id: UUID,
    item_ids: Sequence[UUID],
    *,
    target_product_id: UUID | None = None,
    new: NewProduct | None = None,
    move_keys: bool = True,
) -> SplitResult:
    """Move ``item_ids`` off ``product_id`` onto an existing product or a new one.

    One transaction, committed here; broadcasts and the source's auto-add check run after
    the commit. Scheduling a new target's background pipeline is the caller's (it needs the
    request's background tasks).

    Raises:
        UnknownProduct: The product or the existing target does not exist.
        InvalidSplit: No items, an item not on this product, the target is the source,
            an unknown category or an empty name.
        NameExists: The new name already means a product (model-taught names included).
    """
    ids = list(dict.fromkeys(item_ids))
    source = await crud_product.get_product(db, product_id)
    if source is None:
        raise UnknownProduct(product_id)
    existing_target, new_name = await _validate_target(
        db, product_id, target_product_id, new
    )
    if not ids:
        raise InvalidSplit("No items to move")
    on_product = set(
        (
            await db.execute(
                select(InventoryItem.id)
                .where(InventoryItem.id.in_(ids))
                .where(InventoryItem.product_master_id == product_id)
            )
        )
        .scalars()
        .all()
    )
    strays = [str(item_id) for item_id in ids if item_id not in on_product]
    if strays:
        raise InvalidSplit(f"Not items of this product: {', '.join(strays)}")
    if existing_target is None:
        named = await product_for_name(db, new_name, trust_model=True)
        if named is not None:
            raise NameExists(cast(UUID, named.id), str(named.canonical_name))

    try:
        # Products before items, the order learning locks in (`lock_product`)
        await lock_product(db, product_id)
        record: dict[str, Any] = {
            "aliases": [],
            "names": [],
            "shelf_lives": {str(product_id): _shelf_life(source)},
        }
        if existing_target is not None:
            await lock_product(db, cast(UUID, existing_target.id))
            record["shelf_lives"][str(existing_target.id)] = _shelf_life(
                existing_target
            )

        items = list(
            (
                await db.execute(
                    select(InventoryItem)
                    .where(InventoryItem.id.in_(ids))
                    .order_by(InventoryItem.purchase_date, InventoryItem.created_at)
                    .with_for_update(of=InventoryItem)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        if len(items) != len(ids) or any(
            item.product_master_id != product_id for item in items
        ):
            raise InvalidSplit("The items changed product while this was being asked")
        receipts = await _receipts(db, items)

        if existing_target is None:
            target = await _create_target(
                db, new_name, cast(NewProduct, new), items, receipts
            )
        else:
            target = existing_target
        target_id = cast(UUID, target.id)

        for item in items:
            cast(Any, item).product_master_id = target_id
        await db.execute(
            update(ConsumptionLog)
            .where(ConsumptionLog.inventory_item_id.in_(ids))
            .where(ConsumptionLog.product_master_id == product_id)
            .values(product_master_id=target_id)
            .execution_options(synchronize_session=False)
        )

        moved_keys: list[MovedKey] = []
        if move_keys:
            moved_keys = await _move_keys(db, source, target, items, receipts, record)

        redated = await _relearn(db, [source, target])
        reassignment = await crud_reassignment.record_reassignment(
            db,
            from_product_id=product_id,
            to_product_id=target_id,
            target_created=existing_target is None,
            item_ids=ids,
            keys=record,
        )
        observations_left = await count_observations(db, product_id)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    for product in (source, target):
        await db.refresh(product)
        await db.refresh(product, attribute_names=["display_name_rows"])

    logger.info(
        "Items split off a product",
        extra={
            "reassignment_id": str(reassignment.id),
            "source_id": str(product_id),
            "target_id": str(target_id),
            "target_created": existing_target is None,
            "items": len(ids),
            "keys": len(moved_keys),
        },
    )
    await _broadcast(
        items, source=source, target=target, redated=redated, moved_to=target
    )
    await min_stock.after_stock_decrease(db, product_id)

    return SplitResult(
        reassignment_id=cast(UUID, reassignment.id),
        source=source,
        target=target,
        target_created=existing_target is None,
        moved_item_ids=ids,
        moved_keys=moved_keys,
        source_shelf_life=SourceShelfLife(
            days=int(source.default_shelf_life_days),
            source=str(source.shelf_life_source),
            observations_left=observations_left,
        ),
    )


async def _create_target(
    db: AsyncSession,
    name: str,
    new: NewProduct,
    items: Sequence[InventoryItem],
    receipts: dict[Any, Receipt],
) -> ProductMaster:
    """The new product, made the way quick add makes one, from the moved line's estimates."""
    first: Any = items[0]
    line: dict[str, Any] = {}
    for item in items:
        line = _line(receipts.get(item.receipt_id), cast(Any, item).receipt_line_index)
        if line:
            break
    product, _ = await ProductResolver(db).resolve(
        name=name,
        category=new.category,
        unit=str(first.unit),
        quantity=first.initial_quantity,
        piece_grams=line.get("piece_grams"),
        pack_grams=line.get("pack_grams"),
        shelf_life_days=line.get("shelf_life_days"),
        opened_shelf_life_days=line.get("opened_shelf_life_days"),
    )
    return product


async def _relearn(
    db: AsyncSession, products: Sequence[ProductMaster]
) -> list[tuple[MovedInventoryItem, ProductMaster]]:
    """Re-learn each product's shelf life and re-date its calculated stock."""
    redated: list[tuple[MovedInventoryItem, ProductMaster]] = []
    for product in products:
        learned = await learn_shelf_life(db, cast(UUID, product.id))
        if learned is not None:
            redated.extend((moved, product) for moved in learned.moved)
        redated.extend(
            (moved, product)
            for moved in await recompute_expiry_for_product(db, product)
        )
    return redated


async def _broadcast(
    items: Sequence[InventoryItem],
    *,
    source: ProductMaster,
    target: ProductMaster,
    redated: Sequence[tuple[MovedInventoryItem, ProductMaster]],
    moved_to: ProductMaster,
    product_ids: Sequence[UUID] | None = None,
) -> None:
    """`inventory_update` for every moved or re-dated item, `product_update` for both."""
    announced: set[Any] = set()
    for item in items:
        row: Any = item
        announced.add(row.id)
        await broadcast_inventory_update(
            inventory_item_id=row.id,
            action="updated",
            current_quantity=row.current_quantity,
            status=str(row.status),
            product_name=str(moved_to.canonical_name),
        )
    for moved, product in redated:
        if moved.id in announced:
            continue
        announced.add(moved.id)
        await broadcast_inventory_update(
            inventory_item_id=moved.id,
            action="updated",
            current_quantity=moved.current_quantity,
            status=str(moved.status),
            product_name=str(product.canonical_name),
        )
    names = {
        source.id: str(source.canonical_name),
        target.id: str(target.canonical_name),
    }
    for product_id in product_ids or [cast(UUID, source.id), cast(UUID, target.id)]:
        await broadcast_product_update(
            product_id=product_id, action="updated", product_name=names.get(product_id)
        )


# --- Undo -------------------------------------------------------------------------------


async def _restore_keys(db: AsyncSession, keys: dict[str, Any], to_id: UUID) -> None:
    for entry in reversed(keys.get("aliases") or []):
        alias: Any = await db.get(StoreProductAlias, UUID(entry["id"]))
        if alias is None:
            continue
        if entry.get("created"):
            if alias.product_master_id == to_id:
                await db.delete(alias)
            continue
        previous = entry["previous"]
        alias.product_master_id = UUID(previous["product_master_id"])
        alias.source = previous["source"]
        alias.manually_verified = previous["manually_verified"]
        alias.confidence_score = previous["confidence_score"]

    for entry in keys.get("names") or []:
        taken = (
            await db.execute(
                select(ProductName.id).where(ProductName.name == entry["name"])
            )
        ).first()
        if taken is not None:
            # Learned again since, by something else: that claim stands.
            continue
        db.add(
            ProductName(
                product_master_id=UUID(entry["product_master_id"]),
                name=entry["name"],
                source=entry["source"],
            )
        )
    await db.flush()


async def undo_split(db: AsyncSession, reassignment_id: UUID) -> UndoResult:
    """Replay a split backwards: items, their history and keys go back, and both products
    re-learn their shelf life. A product the split created is deleted when nothing else
    refers to it any more.

    Raises:
        UnknownReassignment: No such record.
        StaleReassignment: Already undone, a side was deleted since, or a moved item is
            no longer on the split's target.
    """
    record = await crud_reassignment.get_reassignment_for_update(db, reassignment_id)
    if record is None:
        raise UnknownReassignment(reassignment_id)
    row: Any = record
    if row.undone_at is not None:
        raise StaleReassignment("This split was already undone")
    from_id = cast(UUID | None, row.from_product_id)
    to_id = cast(UUID | None, row.to_product_id)
    if from_id is None or to_id is None:
        raise StaleReassignment("A product of this split no longer exists")
    ids = [UUID(item_id) for item_id in row.item_ids]
    current = (
        await db.execute(
            select(InventoryItem.product_master_id).where(InventoryItem.id.in_(ids))
        )
    ).scalars()
    if any(product_id != to_id for product_id in current):
        raise StaleReassignment("An item has changed product since the split")

    try:
        source = await lock_product(db, from_id)
        target = await lock_product(db, to_id)
        if source is None or target is None:
            raise StaleReassignment("A product of this split no longer exists")
        items = list(
            (
                await db.execute(
                    select(InventoryItem)
                    .where(InventoryItem.id.in_(ids))
                    .with_for_update(of=InventoryItem)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        if any(item.product_master_id != to_id for item in items):
            raise StaleReassignment("An item has changed product since the split")
        restored = [cast(UUID, item.id) for item in items]
        for item in items:
            cast(Any, item).product_master_id = from_id
        await db.execute(
            update(ConsumptionLog)
            .where(ConsumptionLog.inventory_item_id.in_(restored))
            .where(ConsumptionLog.product_master_id == to_id)
            .values(product_master_id=from_id)
            .execution_options(synchronize_session=False)
        )

        keys: dict[str, Any] = dict(row.keys or {})
        await _restore_keys(db, keys, to_id)
        created = bool(row.target_created)
        for product in (source, target):
            if created and product is target:
                continue
            before = (keys.get("shelf_lives") or {}).get(str(product.id))
            if before:
                product_row: Any = product
                product_row.default_shelf_life_days = before["days"]
                product_row.shelf_life_source = before["source"]
        redated = await _relearn(db, [source, target])

        deleted = False
        if created and not await references_to_product(db, to_id):
            await db.delete(target)
            deleted = True
        crud_reassignment.mark_undone(record)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    await db.refresh(source)
    logger.info(
        "Split undone",
        extra={
            "reassignment_id": str(reassignment_id),
            "source_id": str(from_id),
            "target_id": str(to_id),
            "items": len(restored),
            "target_deleted": deleted,
        },
    )
    await _broadcast(
        items,
        source=source,
        target=target,
        redated=redated,
        moved_to=source,
        product_ids=[from_id, to_id],
    )
    if not deleted:
        await min_stock.after_stock_decrease(db, to_id)

    return UndoResult(reassignment_id=reassignment_id, restored_item_ids=restored)
