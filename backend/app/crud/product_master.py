"""CRUD operations for ProductMaster model."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.shopping_list_item import ShoppingListItem
from app.models.store_product_alias import StoreProductAlias
from app.schemas.product_master import ProductMasterCreate, ProductMasterUpdate
from app.services.product_names import learn_product_name, normalize_product_name
from app.services.units import unit_type_for


def _unit_type(unit: str) -> str:
    """volume, weight or count for a unit; unknown units fall back to count."""
    try:
        return unit_type_for(unit)
    except ValueError:
        return "count"


async def get_products(
    db: AsyncSession, search: str | None = None
) -> list[ProductMaster]:
    """Get all products with optional search filter.

    Args:
        db: Database session.
        search: Optional search string to filter by canonical_name.

    Returns:
        List of products matching the filter.
    """
    query = select(ProductMaster)

    if search:
        query = query.where(ProductMaster.canonical_name.ilike(f"%{search}%"))

    query = query.order_by(ProductMaster.canonical_name)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_product(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Get a product by ID.

    Args:
        db: Database session.
        product_id: Product UUID.

    Returns:
        Product if found, None otherwise.
    """
    result = await db.execute(
        select(ProductMaster).where(ProductMaster.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_product_by_barcode(
    db: AsyncSession, barcode: str
) -> ProductMaster | None:
    """Get a product by barcode (off_product_id).

    Args:
        db: Database session.
        barcode: Barcode/OFF product ID.

    Returns:
        Product if found, None otherwise.
    """
    result = await db.execute(
        select(ProductMaster).where(ProductMaster.off_product_id == barcode)
    )
    return result.scalar_one_or_none()


async def create_product(
    db: AsyncSession, product: ProductMasterCreate
) -> ProductMaster:
    """Create a new product.

    Args:
        db: Database session.
        product: Product data.

    Returns:
        Created product.

    Raises:
        IntegrityError: If foreign key constraint fails (invalid category).
    """
    db_product = ProductMaster(**product.model_dump())
    db.add(db_product)
    await db.flush()
    # A product nobody can look up by name is invisible to resolution (H11).
    await learn_product_name(
        db, db_product, str(db_product.canonical_name), "canonical"
    )
    await db.commit()
    await db.refresh(db_product)
    return db_product


async def update_product(
    db: AsyncSession, product_id: UUID, product_update: ProductMasterUpdate
) -> ProductMaster | None:
    """Update a product.

    Args:
        db: Database session.
        product_id: Product UUID.
        product_update: Fields to update.

    Returns:
        Updated product if found, None otherwise.
    """
    db_product = await get_product(db, product_id)
    if not db_product:
        return None

    # Update only provided fields
    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)

    await db.commit()
    await db.refresh(db_product)
    return db_product


async def references_to_product(db: AsyncSession, product_id: UUID) -> dict[str, int]:
    """Count the rows that would block deleting this product, by table.

    Every foreign key to product_master is NO ACTION (H22 gives each one an
    explicit rule), so deleting a referenced product raises instead of cascading.
    Confirming a receipt writes a store_product_alias row for each product, so in
    practice nearly every real product has at least one reference.
    """
    counts: dict[str, int] = {}
    for model in (InventoryItem, StoreProductAlias, ShoppingListItem, ConsumptionLog):
        total = await db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.product_master_id == product_id)
        )
        if total:
            counts[model.__tablename__] = int(total)
    return counts


async def delete_product(db: AsyncSession, product_id: UUID) -> bool:
    """Delete a product.

    Args:
        db: Database session.
        product_id: Product UUID.

    Returns:
        True if deleted, False if not found.
    """
    db_product = await get_product(db, product_id)
    if not db_product:
        return False

    await db.delete(db_product)
    await db.commit()
    return True


@dataclass(frozen=True)
class MovedInventoryItem:
    """What a broadcast needs to know about an item the merge re-pointed."""

    id: UUID
    current_quantity: Decimal
    status: str


@dataclass
class MergeResult:
    """What one merge moved, dropped and deleted."""

    source_id: UUID
    source_name: str
    target: ProductMaster
    moved: dict[str, int]
    dropped: dict[str, int]
    inventory_items: list[MovedInventoryItem]


def _fold_alias_evidence(kept: StoreProductAlias, gone: StoreProductAlias) -> None:
    """Merge two aliases for the same printed name into the one that stays.

    Dropping the duplicate outright would throw away whatever the cook confirmed
    on it, so the evidence moves even though the row does not.
    """
    keep: Any = kept
    dropped: Any = gone
    keep.occurrence_count = int(keep.occurrence_count or 0) + int(
        dropped.occurrence_count or 0
    )
    keep.manually_verified = bool(keep.manually_verified) or bool(
        dropped.manually_verified
    )
    keep.confidence_score = max(
        float(keep.confidence_score or 0.0), float(dropped.confidence_score or 0.0)
    )
    if dropped.last_seen is not None and (
        keep.last_seen is None or dropped.last_seen > keep.last_seen
    ):
        keep.last_seen = dropped.last_seen


async def _move_aliases(
    db: AsyncSession, source_id: UUID, target_id: UUID
) -> tuple[int, int]:
    """Re-point the source's receipt-name aliases, keeping one row per printed name.

    `store_product_alias` has no unique key on (store_chain, receipt_name) yet -
    H14 adds one - so a collision would not raise today, it would simply leave two
    rows the resolver has to choose between, and break the moment the constraint
    lands. One row per (chain, printed name) is the invariant either way.
    """
    kept: dict[tuple[str, str], StoreProductAlias] = {
        (str(alias.store_chain), str(alias.receipt_name)): alias
        for alias in (
            await db.execute(
                select(StoreProductAlias).where(
                    StoreProductAlias.product_master_id == target_id
                )
            )
        )
        .scalars()
        .all()
    }

    moved = dropped = 0
    source_aliases = (
        (
            await db.execute(
                select(StoreProductAlias).where(
                    StoreProductAlias.product_master_id == source_id
                )
            )
        )
        .scalars()
        .all()
    )
    for alias in source_aliases:
        key = (str(alias.store_chain), str(alias.receipt_name))
        collision = kept.get(key)
        if collision is None:
            row: Any = alias
            row.product_master_id = target_id
            kept[key] = alias
            moved += 1
        else:
            _fold_alias_evidence(collision, alias)
            await db.delete(alias)
            dropped += 1
    return moved, dropped


async def _move_names(
    db: AsyncSession, source: ProductMaster, target: ProductMaster
) -> tuple[int, int]:
    """Re-point the source's names, dropping the ones the catalog already has.

    `product_name` is UNIQUE (name), so a name the catalog already knows cannot
    move: the row that is there already means the same thing, and the duplicate
    goes rather than failing the merge. The unique index makes two rows for one
    name impossible today, so the only duplicate a real merge meets is the
    source's canonical name, claimed by the target while the source has no name
    row of its own - Open Food Facts enrichment writes straight to
    `product_master`. The check covers both.

    The canonical row goes too, rather than moving: the target has a canonical name
    of its own, and the source's becomes a synonym with its own provenance (below).
    """
    source_id = cast(UUID, source.id)
    target_id = cast(UUID, target.id)
    canonical_key = normalize_product_name(str(source.canonical_name))

    names = (
        (
            await db.execute(
                select(ProductName).where(ProductName.product_master_id == source_id)
            )
        )
        .scalars()
        .all()
    )
    claimed = {
        str(name)
        for name in (
            await db.execute(
                select(ProductName.name).where(
                    ProductName.name.in_([str(name.name) for name in names]),
                    ProductName.product_master_id != source_id,
                )
            )
        )
        .scalars()
        .all()
    }

    moved = dropped = 0
    for product_name in names:
        key = str(product_name.name)
        if key == canonical_key or key in claimed:
            await db.delete(product_name)
            if key != canonical_key:
                dropped += 1
        else:
            row: Any = product_name
            row.product_master_id = target_id
            moved += 1
    await db.flush()

    # A merge is the cook's own act, so the name they merged away is a cook-sourced
    # synonym - unless the target already knew it, in which case the first claim wins.
    if await learn_product_name(db, target, str(source.canonical_name), "cook"):
        moved += 1
    else:
        dropped += 1
    return moved, dropped


async def merge_product_rows(
    db: AsyncSession, source: ProductMaster, target: ProductMaster
) -> MergeResult:
    """Re-point everything that refers to ``source`` at ``target``, then delete it.

    One transaction: the caller commits, so a failure anywhere leaves the catalog
    exactly as it was. Nothing here validates - `services.product_merge` decides
    whether a merge is allowed at all.
    """
    source_id = cast(UUID, source.id)
    target_id = cast(UUID, target.id)
    result = MergeResult(
        source_id=source_id,
        source_name=str(source.canonical_name),
        target=target,
        moved={},
        dropped={},
        inventory_items=[],
    )

    inventory_rows = (
        await db.execute(
            update(InventoryItem)
            .where(InventoryItem.product_master_id == source_id)
            .values(product_master_id=target_id)
            .returning(
                InventoryItem.id,
                InventoryItem.current_quantity,
                InventoryItem.status,
            )
            .execution_options(synchronize_session=False)
        )
    ).all()
    result.inventory_items = [
        MovedInventoryItem(id=row[0], current_quantity=row[1], status=str(row[2]))
        for row in inventory_rows
    ]
    result.moved[InventoryItem.__tablename__] = len(result.inventory_items)

    moved_aliases, dropped_aliases = await _move_aliases(db, source_id, target_id)
    result.moved[StoreProductAlias.__tablename__] = moved_aliases
    result.dropped[StoreProductAlias.__tablename__] = dropped_aliases

    moved_names, dropped_names = await _move_names(db, source, target)
    result.moved[ProductName.__tablename__] = moved_names
    result.dropped[ProductName.__tablename__] = dropped_names

    for model in (ShoppingListItem, ConsumptionLog):
        moved = await db.execute(
            update(model)
            .where(model.product_master_id == source_id)
            .values(product_master_id=target_id)
            .returning(model.id)
            .execution_options(synchronize_session=False)
        )
        result.moved[model.__tablename__] = len(moved.all())

    # Only now, with nothing pointing at it, can the row go. Anything missed here
    # would raise on the foreign key rather than be silently orphaned.
    await db.flush()
    await db.delete(source)
    await db.flush()
    return result


async def enrich_product_from_off_data(
    db: AsyncSession, enriched_data: dict
) -> tuple[ProductMaster, bool]:
    """Create or update product from OFF enrichment data.

    Args:
        db: Database session.
        enriched_data: Enriched data from OFF service containing:
            - canonical_name, category, off_product_id, off_data

    Returns:
        Tuple of (product, created) where created is True if new, False if updated.
    """
    barcode = enriched_data["off_product_id"]

    # Check if product with this barcode already exists
    existing_product = await get_product_by_barcode(db, barcode)

    if existing_product:
        # Update existing product
        existing_product.canonical_name = enriched_data["canonical_name"]
        existing_product.category = enriched_data["category"]
        existing_product.off_product_id = enriched_data["off_product_id"]
        existing_product.off_data = enriched_data["off_data"]

        await db.commit()
        await db.refresh(existing_product)
        return existing_product, False
    else:
        # Create new product with sensible defaults
        # Use category defaults from seed data
        from app.crud.category import get_category

        category_defaults = await get_category(db, enriched_data["category"])

        from app.services.storage import storage_type_for_category

        storage_type = storage_type_for_category(enriched_data["category"])

        default_unit = enriched_data.get("default_unit", "pcs")

        new_product = ProductMaster(
            canonical_name=enriched_data["canonical_name"],
            category=enriched_data["category"],
            storage_type=storage_type,
            default_shelf_life_days=category_defaults.default_shelf_life_days
            if category_defaults
            else 365,
            unit_type=_unit_type(default_unit),
            default_unit=default_unit,
            default_quantity=enriched_data.get("default_quantity"),
            off_product_id=enriched_data["off_product_id"],
            off_data=enriched_data["off_data"],
        )

        try:
            db.add(new_product)
            await db.commit()
            await db.refresh(new_product)
            return new_product, True
        except IntegrityError:
            # Concurrent request already created this product — fetch and return it
            await db.rollback()
            existing = await get_product_by_barcode(db, barcode)
            if existing:
                return existing, False
            raise
