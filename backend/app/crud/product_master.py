"""CRUD operations for ProductMaster model."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.models.category import Category
from app.models.consumption_log import ConsumptionLog
from app.models.inventory_item import InventoryItem
from app.models.product_display_name import ProductDisplayName
from app.models.product_emoji_learned import ProductEmojiLearned
from app.models.product_master import EmojiMatch, IconStatus, ProductMaster
from app.models.product_name import ProductName
from app.models.shopping_list_item import ShoppingListItem
from app.models.store_product_alias import StoreProductAlias
from app.schemas.product_master import ProductMasterCreate, ProductMasterUpdate
from app.services.product_names import learn_product_name, normalize_product_name
from app.services.storage import storage_type_for_category
from app.services.units import unit_type_for


def _unit_type(unit: str) -> str:
    """volume, weight or count for a unit; unknown units fall back to count."""
    try:
        return unit_type_for(unit)
    except ValueError:
        return "count"


def _escape_ilike(term: str) -> str:
    """Escape `%`, `_` and the escape character itself, so a literal one in a search term is
    never read as an ILIKE wildcard (F13 review: `?q=` reaches this now, H58).
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def get_products(
    db: AsyncSession, search: str | None = None, emoji_match: str | None = None
) -> list[ProductMaster]:
    """Get all products with optional search filter.

    Args:
        db: Database session.
        search: Optional search string to filter by canonical_name.
        emoji_match: Optional `emoji_match` filter (Q18 build), e.g. "proposed" for the
            review list.

    Returns:
        List of products matching the filter.
    """
    query = select(ProductMaster)

    if search:
        query = query.where(
            ProductMaster.canonical_name.ilike(
                f"%{_escape_ilike(search)}%", escape="\\"
            )
        )
    if emoji_match:
        query = query.where(ProductMaster.emoji_match == emoji_match)

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

    The shelf life is required here, so it is always a number somebody typed: the cook's
    (Q19). It used to be stored as a `category` placeholder, which invited every estimate
    to replace it.

    Raises:
        IntegrityError: If foreign key constraint fails (invalid category).
    """
    db_product = ProductMaster(**product.model_dump(), shelf_life_source="cook")
    db.add(db_product)
    await db.flush()
    # A product nobody can look up by name is invisible to resolution (H11).
    await learn_product_name(
        db, db_product, str(db_product.canonical_name), "canonical"
    )
    await db.commit()
    await _refresh_product(db, db_product)
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

    old_name = str(db_product.canonical_name)
    old_category = str(db_product.category)

    # Update only provided fields. `display_names` is not a plain column - it has no
    # setter, only the read-only `display_names` property - so it is handled on its own,
    # below, through `set_display_name` rather than `setattr`.
    update_data = product_update.model_dump(exclude_unset=True)
    display_names_update = update_data.pop("display_names", None)
    for field, value in update_data.items():
        setattr(db_product, field, value)

    # This is the cook talking, and the loop above cannot tell. A shelf life they typed
    # is a correction: no later estimate may replace it (Q11). Set after the loop so an
    # explicit `shelf_life_source` in the payload cannot claim to be one.
    if "default_shelf_life_days" in update_data:
        db_product.shelf_life_source = "cook"

    if update_data.get("category") not in (None, old_category):
        await _follow_category(db, db_product, update_data)

    if normalize_product_name(str(db_product.canonical_name)) != (
        normalize_product_name(old_name)
    ):
        await _rename_keys(db, db_product, old_name)

    # The cook's own name (PATCH /products/{id}), one language at a time (Post-MVP
    # frontier item 13). Always `cook`: a human typed this request, whatever a model
    # proposed earlier for the same language is now superseded.
    if display_names_update:
        for language, name in display_names_update.items():
            await set_display_name(
                db, db_product, language=language, name=str(name), source="cook"
            )

    await db.commit()
    await _refresh_product(db, db_product)
    return db_product


async def set_display_name(
    db: AsyncSession, product: ProductMaster, *, language: str, name: str, source: str
) -> None:
    """Upsert one language's display name on the product (Post-MVP frontier item 13).

    Flushes but does not commit - the caller's own transaction decides when. Queried by
    table rather than through the `display_name_rows` relationship, so this never depends
    on whether that collection happens to be loaded on `product` already.

    `source` is whatever the caller decided (`cook` from a PATCH, `model` from the
    background proposal in `services/display_names.py`) - this never second-guesses which
    one should win; `services/display_names.py` is where a model proposal checks a cook's
    name is not already there before ever calling this.
    """
    existing = (
        await db.execute(
            select(ProductDisplayName).where(
                ProductDisplayName.product_master_id == product.id,
                ProductDisplayName.language == language,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        row: Any = existing
        row.name = name
        row.source = source
    else:
        db.add(
            ProductDisplayName(
                product_master_id=product.id,
                language=language,
                name=name,
                source=source,
            )
        )
    await db.flush()


async def _refresh_product(db: AsyncSession, product: ProductMaster) -> None:
    """Refresh a just-written product for a response that includes `display_names`.

    Plain `db.refresh()` only refreshes column attributes; a relationship it already
    expires rather than reloads, which would otherwise crash the next (async, so not
    lazy-load-capable) access of `display_names` in API response serialisation. The second
    call is the documented way to force that reload within this same await.
    """
    await db.refresh(product)
    await db.refresh(product, attribute_names=["display_name_rows"])


async def _follow_category(
    db: AsyncSession, product: ProductMaster, update_data: dict[str, Any]
) -> None:
    """A product moved to another category takes what only ever came from the old one (H52).

    Storage decides where new stock goes, so it always follows; what is in the kitchen
    already stays where the cook put it. A placeholder shelf life (`category`) meant
    "what the old category says" and takes the new one's; a number the cook typed or the
    model estimated was about the food, not the category, and stays.
    """
    row: Any = product
    if "storage_type" not in update_data:
        row.storage_type = storage_type_for_category(str(product.category))
    if (
        "default_shelf_life_days" not in update_data
        and str(product.shelf_life_source) == "category"
    ):
        category = await db.get(Category, product.category)
        if category is not None:
            row.default_shelf_life_days = category.default_shelf_life_days


async def _rename_keys(db: AsyncSession, product: ProductMaster, old_name: str) -> None:
    """Keep `product_name` true to a rename (H52).

    The old canonical row becomes the cook's word - the name still finds the product, as
    a merged-away name does, and the cook can now remove it - and the new name is
    learned as canonical. If another product already holds the new name as a cook's or
    canonical key, the first claim wins and the canonical-name fallback in
    `product_for_name` still finds this one by its own name.
    """
    old_row = (
        (
            await db.execute(
                select(ProductName).where(
                    ProductName.product_master_id == product.id,
                    ProductName.name == normalize_product_name(old_name),
                    ProductName.source == "canonical",
                )
            )
        )
        .scalars()
        .first()
    )
    if old_row is not None:
        row: Any = old_row
        row.source = "cook"
        await db.flush()
    if await learn_product_name(db, product, str(product.canonical_name), "canonical"):
        return
    # Renamed back to a word it already answered to: that row is its name again.
    own: Any = (
        (
            await db.execute(
                select(ProductName).where(
                    ProductName.product_master_id == product.id,
                    ProductName.name
                    == normalize_product_name(str(product.canonical_name)),
                )
            )
        )
        .scalars()
        .first()
    )
    if own is not None and str(own.source) != "canonical":
        own.source = "canonical"
        await db.flush()


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
    on it, so the evidence moves even though the row does not. Provenance follows
    H14's precedence - the cook's word first, and a machine mapping never demotes
    one the cook corrected.
    """
    keep: Any = kept
    dropped: Any = gone
    keep.occurrence_count = int(keep.occurrence_count or 0) + int(
        dropped.occurrence_count or 0
    )
    if bool(dropped.manually_verified) and not bool(keep.manually_verified):
        keep.source = dropped.source
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

    One mapping per (chain, printed name) is the invariant H14 put in the schema as
    `uq_store_product_alias_chain_name`, which is why two products cannot normally
    hold the same printed name and a plain move would be enough. A merge is a repair
    though, and must not be the operation that dies on a duplicate the constraint did
    not catch, so a collision collapses to one row instead of raising.
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
        await _refresh_product(db, existing_product)
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
            # Never an estimate on this path - it is the category's figure or a bare
            # guess of a year, and both are placeholders a real one may replace (Q11).
            shelf_life_source="category",
            unit_type=_unit_type(default_unit),
            default_unit=default_unit,
            default_quantity=enriched_data.get("default_quantity"),
            off_product_id=enriched_data["off_product_id"],
            off_data=enriched_data["off_data"],
        )

        try:
            db.add(new_product)
            await db.commit()
            await _refresh_product(db, new_product)
            return new_product, True
        except IntegrityError:
            # Concurrent request already created this product — fetch and return it
            await db.rollback()
            existing = await get_product_by_barcode(db, barcode)
            if existing:
                return existing, False
            raise


# --- the generated icon (Q18-G2) ----------------------------------------------------------


async def get_icon_subject(
    db: AsyncSession, product_id: UUID, *, for_update: bool = False
) -> ProductMaster | None:
    """The product, freshly read, for deciding what its icon job does next.

    Always undefers `icon_image`: callers need to tell "ready with an image" from "ready
    with none" (a pre-Q18-G2 row's old status carried through with nothing behind it), and a
    deferred column read outside an active session would otherwise lazy-load unsafely.
    `for_update=True` takes a row lock (`SELECT ... FOR UPDATE`), so a finishing render can
    re-check "is this still wanted" against a row nothing else is concurrently changing.
    """
    query = (
        select(ProductMaster)
        .where(ProductMaster.id == product_id)
        .options(undefer(ProductMaster.icon_image))
        .execution_options(populate_existing=True)
    )
    if for_update:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def mark_icon_pending(
    db: AsyncSession, product: ProductMaster, seed: int
) -> None:
    """Say a render is on its way (or waiting its turn), with the seed it will use. Commits."""
    product.icon_status = IconStatus.PENDING  # type: ignore[assignment]
    product.icon_seed = seed  # type: ignore[assignment]
    await db.commit()


async def store_icon(
    db: AsyncSession, product: ProductMaster, image: bytes, seed: int
) -> None:
    """Keep a generated image; its version is the moment it was stored. Commits."""
    product.icon_image = image
    product.icon_seed = seed  # type: ignore[assignment]
    product.icon_status = IconStatus.READY  # type: ignore[assignment]
    product.icon_updated_at = datetime.now(UTC)  # type: ignore[assignment]
    await db.commit()


async def mark_icon_failed(db: AsyncSession, product: ProductMaster) -> None:
    """The render failed; any earlier image stays and stays served. Commits."""
    product.icon_status = IconStatus.FAILED  # type: ignore[assignment]
    await db.commit()


async def clear_icon(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Drop the image for the category emoji, as the cook's choice. None: no product."""
    product = await db.get(ProductMaster, product_id)
    if product is None:
        return None
    product.icon_image = None
    product.icon_seed = None  # type: ignore[assignment]
    product.icon_status = IconStatus.CLEARED  # type: ignore[assignment]
    product.icon_updated_at = None  # type: ignore[assignment]
    await db.commit()
    # A plain `db.get()` can hand back an object already in this session's identity map
    # from an earlier load that never touched `display_name_rows` (Post-MVP frontier item
    # 13) - unlike a fresh `select()`, it does not reliably (re)populate a `lazy="selectin"`
    # relationship on its own. Without this, serialising the response crashes instead
    # (`MissingGreenlet`): an async context cannot lazy-load it after the fact.
    await db.refresh(product, attribute_names=["display_name_rows"])
    return product


async def stored_icon(
    db: AsyncSession, product_id: UUID
) -> tuple[bytes, datetime] | None:
    """The stored image and when it last changed; None when there is none to show."""
    row = (
        await db.execute(
            select(ProductMaster.icon_image, ProductMaster.icon_updated_at).where(
                ProductMaster.id == product_id,
                ProductMaster.icon_image.is_not(None),
                ProductMaster.icon_updated_at.is_not(None),
            )
        )
    ).first()
    if row is None:
        return None
    return bytes(row[0]), row[1]


def icon_needs_generation(product: ProductMaster, stale_before: datetime) -> bool:
    """Never generated, failed, pending so long that its job must have died, or `ready`
    with nothing actually behind it (a pre-Q18-G2 row the migration missed, or any future
    bug that leaves the two out of step - belt and suspenders over the migration's backfill).

    Cleared and exact/cook-emoji products are never picked here: `cleared` is the cook's own
    "do not generate this" and an exact or cook emoji already shows on the tile, so an image
    nobody would ever see is not worth a GPU job.
    """
    status = product.icon_status
    if status == IconStatus.CLEARED:
        return False
    if product.emoji_match in (EmojiMatch.EXACT, EmojiMatch.COOK):
        return False
    if status is None or status == IconStatus.FAILED:
        return True
    if status == IconStatus.READY:
        return product.icon_image is None
    return bool(status == IconStatus.PENDING and product.updated_at < stale_before)


async def products_needing_icons(
    db: AsyncSession, stale_before: datetime, limit: int | None = None
) -> list[ProductMaster]:
    """Every product `icon_needs_generation` would pick, oldest first.

    Food-only is not filtered here (it needs a query against `non_food_name`, done at the
    service layer); every candidate this returns is still rechecked there before a job runs.
    """
    not_shown_as_emoji = or_(
        ProductMaster.emoji_match.is_(None),
        ProductMaster.emoji_match.notin_([EmojiMatch.EXACT, EmojiMatch.COOK]),
    )
    query = (
        select(ProductMaster)
        .where(
            # `cleared` matches none of the four conditions below, so it is already
            # excluded without a separate clause - and a separate `!= CLEARED` would wrongly
            # drop every NULL (never-generated) row too, under SQL's three-valued logic.
            not_shown_as_emoji,
            or_(
                ProductMaster.icon_status.is_(None),
                ProductMaster.icon_status == IconStatus.FAILED,
                and_(
                    ProductMaster.icon_status == IconStatus.PENDING,
                    ProductMaster.updated_at < stale_before,
                ),
                # `ready` with nothing behind it: belt and suspenders over the migration's
                # own backfill (icon_needs_generation's docstring has the full reasoning).
                and_(
                    ProductMaster.icon_status == IconStatus.READY,
                    ProductMaster.icon_image.is_(None),
                ),
            ),
        )
        .order_by(ProductMaster.created_at, ProductMaster.id)
    )
    if limit is not None:
        query = query.limit(limit)
    return list((await db.execute(query)).scalars().all())


# --- the exact emoji (Q18 build) ----------------------------------------------------------


class EmojiNotProposed(Exception):
    """Confirm or reject was asked of a product whose emoji is not `proposed`."""


async def get_emoji_subject(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """The product, freshly read, for deciding what its emoji does next."""
    return await db.get(ProductMaster, product_id, populate_existing=True)


async def set_emoji(
    db: AsyncSession, product: ProductMaster, *, emoji: str | None, match: EmojiMatch
) -> None:
    """Set the product's emoji and match together, whatever decided them. Commits."""
    row: Any = product
    row.emoji = emoji
    row.emoji_match = match.value
    await db.commit()


async def confirm_emoji_proposal(
    db: AsyncSession, product_id: UUID
) -> ProductMaster | None:
    """A `proposed` emoji becomes `exact`. None: no such product.

    Raises:
        EmojiNotProposed: the product's emoji is not `proposed`.
    """
    product = await get_emoji_subject(db, product_id)
    if product is None:
        return None
    if product.emoji_match != EmojiMatch.PROPOSED:
        raise EmojiNotProposed(f"product '{product_id}' has no emoji to confirm")
    row: Any = product
    row.emoji_match = EmojiMatch.EXACT.value
    await db.commit()
    await _refresh_product(db, product)
    return product


async def reject_emoji_proposal(
    db: AsyncSession, product_id: UUID
) -> ProductMaster | None:
    """A `proposed` emoji becomes `none`, and the emoji itself is dropped. None: no product.

    Raises:
        EmojiNotProposed: the product's emoji is not `proposed`.
    """
    product = await get_emoji_subject(db, product_id)
    if product is None:
        return None
    if product.emoji_match != EmojiMatch.PROPOSED:
        raise EmojiNotProposed(f"product '{product_id}' has no emoji to reject")
    row: Any = product
    row.emoji = None
    row.emoji_match = EmojiMatch.NONE.value
    await db.commit()
    await _refresh_product(db, product)
    return product


async def set_cook_emoji(
    db: AsyncSession, product_id: UUID, emoji: str | None
) -> ProductMaster | None:
    """The cook's own choice: an emoji (`cook`), or none at all (`cleared`). Commits."""
    product = await get_emoji_subject(db, product_id)
    if product is None:
        return None
    row: Any = product
    if emoji is None:
        row.emoji = None
        row.emoji_match = EmojiMatch.CLEARED.value
    else:
        row.emoji = emoji
        row.emoji_match = EmojiMatch.COOK.value
    await db.commit()
    await _refresh_product(db, product)
    return product


async def get_learned_emoji(db: AsyncSession, generic_name_key: str) -> str | None:
    """A confirmed proposal's emoji for this normalised generic name, or None."""
    row = (
        await db.execute(
            select(ProductEmojiLearned.emoji).where(
                ProductEmojiLearned.generic_name == generic_name_key
            )
        )
    ).first()
    return None if row is None else str(row[0])


async def learn_emoji(db: AsyncSession, generic_name_key: str, emoji: str) -> None:
    """Remember a confirmed proposal, so this generic name is never asked again. Commits.

    A name already learned keeps its first answer - a confirm can only ever agree with
    the name's own earlier confirmation, since the curated table and this table are both
    checked before any product of that name is ever proposed one again.
    """
    existing = (
        await db.execute(
            select(ProductEmojiLearned).where(
                ProductEmojiLearned.generic_name == generic_name_key
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(ProductEmojiLearned(generic_name=generic_name_key, emoji=emoji))
        await db.commit()


# --- display names (Post-MVP frontier item 13) ---------------------------------------------


async def get_display_name_subject(
    db: AsyncSession, product_id: UUID
) -> ProductMaster | None:
    """The product, freshly read, for deciding what its display-name proposal does next.

    `populate_existing=True`, exactly as `get_emoji_subject` does: the background proposal
    reads this once before asking the model and once more right before it writes, and the
    second read must see a cook's own edit that landed in between - not a stale copy already
    in this session's identity map from the first read.
    """
    return await db.get(ProductMaster, product_id, populate_existing=True)
