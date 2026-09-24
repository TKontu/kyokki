"""Resolving and learning the names that mean a product.

The key half of `docs/PRODUCT_RESOLUTION_SPEC.md`: a line resolves to a product through an
exact key, never through a similarity score. This module owns the key format and the two
operations on it - look a name up, and learn a new one.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName

logger = get_logger(__name__)


@dataclass(frozen=True)
class KnownName:
    """A product a name means, and whose word that was (H51).

    `source` is the `product_name` row's: `canonical` (the product's own name, or the
    fallback for a product with no row), `cook`, or `model`. Resolution needs it because
    a synonym the model taught pre-fills a row but is not the cook's word.
    """

    product: ProductMaster
    source: str


def normalize_product_name(name: str | None) -> str:
    """The lookup key: casefolded, whitespace collapsed.

    Deliberately gentler than `normalize_receipt_name`, which also strips a trailing
    price because it keys *printed* names. These are catalog names.
    """
    return " ".join((name or "").split()).casefold()


async def product_for_name(
    db: AsyncSession, name: str | None, *, trust_model: bool = True
) -> ProductMaster | None:
    """The product this name means, or None. An exact key, never a score.

    Falls back to the canonical name itself for rows written without a `product_name`
    row - the backfill migration covers everything that existed, but the fallback keeps
    resolution correct for anything that slips past `learn_product_name` later.

    `trust_model=False` ignores synonyms the model taught (H51): a cook who types
    "Ketchup" as a new product has just refused the product a model once guessed for
    that word, and must not be handed it again.
    """
    key = normalize_product_name(name)
    if not key:
        return None

    query = (
        select(ProductMaster)
        .join(ProductName, ProductName.product_master_id == ProductMaster.id)
        .where(ProductName.name == key)
    )
    if not trust_model:
        query = query.where(ProductName.source != "model")
    by_key = (await db.execute(query)).scalars().first()
    if by_key is not None:
        return by_key

    return (
        (
            await db.execute(
                select(ProductMaster)
                .where(func.lower(func.btrim(ProductMaster.canonical_name)) == key)
                .order_by(ProductMaster.created_at)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def known_names(db: AsyncSession, names: Iterable[str]) -> dict[str, KnownName]:
    """Resolve many names at once, keyed by their normalised form, with their source.

    One query for a whole receipt instead of one per line - the matcher this replaces
    loaded every product and every alias in the database for each receipt.

    Falls back to canonical names for the same reason `product_for_name` does: the
    backfill migration covers everything that existed, but products written straight
    to `product_master` - Open Food Facts enrichment, say - have no `product_name` row
    and would otherwise be unresolvable.
    """
    keys = {normalize_product_name(name) for name in names}
    keys.discard("")
    if not keys:
        return {}

    found: dict[str, KnownName] = {}
    rows = (
        await db.execute(
            select(ProductName.name, ProductName.source, ProductMaster)
            .join(ProductMaster, ProductName.product_master_id == ProductMaster.id)
            .where(ProductName.name.in_(keys))
        )
    ).all()
    for key, source, product in rows:
        found[str(key)] = KnownName(product=product, source=str(source))

    missing = keys - set(found)
    if missing:
        canonical = (
            await db.execute(
                select(
                    func.lower(func.btrim(ProductMaster.canonical_name)),
                    ProductMaster,
                ).where(
                    func.lower(func.btrim(ProductMaster.canonical_name)).in_(missing)
                )
            )
        ).all()
        for key, product in canonical:
            found.setdefault(str(key), KnownName(product=product, source="canonical"))

    return found


async def learn_product_name(
    db: AsyncSession,
    product: ProductMaster,
    name: str | None,
    source: str = "model",
) -> bool:
    """Record that ``name`` means ``product``. Returns True when a row was added or
    re-pointed.

    Among the cook's and canonical rows the first claim wins, and the cook resolves a
    genuine clash with a merge (spec §3.7). A row the *model* taught is different (H51,
    Q13): it was a guess the cook merely did not contradict, so a cook's word or a
    product's own name for the same key displaces it - otherwise "ketchup", once guessed
    for Taco sauce, stayed Taco sauce for ever, whatever the cook did afterwards.

    Re-learning a name the product already has is a no-op, so confirm can call this
    unconditionally; the one exception upgrades a model row to the cook's word in place,
    which adds nothing and returns False (merge counts on that).
    """
    key = normalize_product_name(name)
    if not key:
        return False

    existing = (
        (await db.execute(select(ProductName).where(ProductName.name == key)))
        .scalars()
        .first()
    )
    if existing is not None:
        row: Any = existing  # Column-typed model: assign plain values
        if existing.product_master_id == product.id:
            if str(existing.source) == "model" and source == "cook":
                row.source = source
                await db.flush()
            return False
        if str(existing.source) == "model" and source != "model":
            logger.info(
                "Name re-pointed from a model guess",
                extra={
                    "product_name": key,
                    "was": str(existing.product_master_id),
                    "now": str(product.id),
                    "source": source,
                },
            )
            row.product_master_id = product.id
            row.source = source
            await db.flush()
            return True
        logger.info(
            "Name already means another product; leaving it alone",
            extra={
                "product_name": key,
                "claimed_by": str(existing.product_master_id),
                "offered": str(product.id),
            },
        )
        return False

    db.add(ProductName(product_master_id=product.id, name=key, source=source))
    await db.flush()
    return True


class UnknownName(LookupError):
    """No such name row, or it belongs to another product."""


class CanonicalName(ValueError):
    """The product's own name: it is changed by renaming the product, not removed."""


async def names_for_product(db: AsyncSession, product_id: UUID) -> list[ProductName]:
    """Every name that resolves to this product, its own name first (H52)."""
    rows = (
        (
            await db.execute(
                select(ProductName)
                .where(ProductName.product_master_id == product_id)
                .order_by(ProductName.source != "canonical", ProductName.name)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def forget_product_name(
    db: AsyncSession, product_id: UUID, name_id: UUID
) -> None:
    """Remove a learned name, so the word stops meaning this product (H52).

    The cleanup path for keys H51 could not reach: a synonym written before it - "ketchup"
    for Taco sauce - was the cook's word as far as the table knew. The next line with the
    word goes back through selection.
    """
    row = await db.get(ProductName, name_id)
    if row is None or row.product_master_id != product_id:
        raise UnknownName(str(name_id))
    if str(row.source) == "canonical":
        raise CanonicalName(str(row.name))
    forgotten = {
        "product_name": str(row.name),
        "product_id": str(product_id),
        "source": str(row.source),
    }
    await db.delete(row)
    await db.commit()
    logger.info("Product name forgotten", extra=forgotten)
