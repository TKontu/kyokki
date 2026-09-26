"""Names in, decisions out: resolving and teaching product names for agents (AG2).

The rule is the catalog's own (`docs/PRODUCT_RESOLUTION_SPEC.md` §2): a name means a product
only through an exact key - its canonical name or a learned `product_name`. A near miss is
never taken for a hit. It is offered back as candidates, and the caller decides.
"""

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.models.product_master import ProductMaster
from app.models.product_name import NameSource, ProductName
from app.schemas.product_names import ProductNameEntry
from app.schemas.stock import (
    ProductCandidate,
    ProductMatch,
    ResolveResponse,
)
from app.services import idempotency
from app.services.idempotency import IdempotencyClaim
from app.services.product_names import (
    known_names,
    learn_product_name,
    normalize_product_name,
    product_for_name,
)
from app.services.product_resolution import ResolvableLine, TrigramRetriever

logger = get_logger(__name__)


class ProductNotFound(LookupError):
    """No product has this id, or nothing in the catalog is even like this name."""

    def __init__(self, message: str, *, by_name: bool) -> None:
        super().__init__(message)
        self.by_name = by_name


class AmbiguousProduct(LookupError):
    """No exact name hit, but products like it exist: the caller has to choose."""

    def __init__(self, name: str, candidates: list[ProductCandidate]) -> None:
        super().__init__(f"No product is called {name!r}; did you mean one of these?")
        self.candidates = candidates


class NameTaken(ValueError):
    """The name already means another product; a merge, not a teach, settles that."""

    def __init__(self, name: str, owner: ProductMaster) -> None:
        # Plain values: the session is rolled back before anyone reads them.
        self.owner_id: UUID = owner.id  # type: ignore[assignment]
        self.owner_name = str(owner.canonical_name)
        super().__init__(
            f"{name!r} already means {self.owner_name!r} ({self.owner_id})"
        )


# Each candidate's closest name and how close, scored the way `TrigramRetriever` ranks them.
_SCORES = text(
    """
    WITH keys AS (
        SELECT pn.product_master_id AS pid, pn.name AS key, pn.source AS source
        FROM product_name pn
        WHERE pn.product_master_id = ANY(:ids)
        UNION ALL
        SELECT pm.id, lower(btrim(pm.canonical_name)), 'canonical'
        FROM product_master pm
        WHERE pm.id = ANY(:ids)
    )
    SELECT DISTINCT ON (pid) pid, source,
           greatest(similarity(key, :n), word_similarity(key, :n),
                    word_similarity(:n, key)) AS score
    FROM keys
    ORDER BY pid, score DESC, (source = 'canonical') DESC
    """
).bindparams(bindparam("ids", type_=ARRAY(PG_UUID(as_uuid=True))))


async def candidates_for(db: AsyncSession, name: str) -> list[ProductCandidate]:
    """Products like this name, best first, with a score and whose name was closest."""
    shortlist = await TrigramRetriever(db).candidates(
        ResolvableLine(line_id="agent", printed=name)
    )
    if not shortlist:
        return []
    rows = (
        await db.execute(
            _SCORES,
            {
                "ids": [c.product_id for c in shortlist],
                "n": normalize_product_name(name),
            },
        )
    ).all()
    scored = {pid: (str(source), float(score or 0)) for pid, source, score in rows}
    return [
        ProductCandidate(
            product_id=c.product_id,
            name=c.name,
            source=scored.get(c.product_id, ("canonical", 0.0))[0],
            score=round(scored.get(c.product_id, ("canonical", 0.0))[1], 3),
        )
        for c in shortlist
    ]


async def _exact(db: AsyncSession, name: str) -> ProductMatch | None:
    product = await product_for_name(db, name)
    if product is None:
        return None
    known = (await known_names(db, [name])).get(normalize_product_name(name))
    source = (
        known.source
        if known is not None and known.product.id == product.id
        else NameSource.CANONICAL.value
    )
    return ProductMatch(
        product_id=product.id,  # type: ignore[arg-type]
        name=str(product.canonical_name),
        source=source,
    )


async def resolve(db: AsyncSession, name: str) -> ResolveResponse:
    """The exact hit for a name if there is one, the products like it, and what to create."""
    match = await _exact(db, name)
    return ResolveResponse(
        match=match,
        candidates=await candidates_for(db, name),
        suggestion=None if match else (normalize_product_name(name) or None),
    )


async def product_for_request(
    db: AsyncSession, *, name: str | None, product_id: UUID | None
) -> ProductMaster:
    """The product a request means, by id or by exact name; never by a score.

    Raises:
        ProductNotFound: Unknown id, or a name nothing in the catalog resembles.
        AmbiguousProduct: No exact hit, but candidates to choose from.
    """
    if product_id is not None:
        product = await crud_product.get_product(db, product_id)
        if product is None:
            raise ProductNotFound(f"No product with id {product_id}", by_name=False)
        return product

    product = await product_for_name(db, name)
    if product is not None:
        return product
    candidates = await candidates_for(db, name or "")
    if candidates:
        raise AmbiguousProduct(name or "", candidates)
    raise ProductNotFound(f"No product is called {name!r}", by_name=True)


@dataclass(frozen=True)
class TaughtName:
    created: bool
    entry: ProductNameEntry

    @property
    def status_code(self) -> int:
        return 201 if self.created else 200


def _entry(row: Any) -> ProductNameEntry:
    return ProductNameEntry(
        id=row.id,
        name=row.name,
        source=row.source,
        removable=row.source != NameSource.CANONICAL,
    )


async def _teach(
    db: AsyncSession, product_id: UUID, key: str, claim: IdempotencyClaim | None
) -> TaughtName:
    """`teach_name`'s work in the open transaction; does not commit."""
    product = await crud_product.get_product(db, product_id)
    if product is None:
        raise ProductNotFound(f"No product with id {product_id}", by_name=False)
    owner = await product_for_name(db, key, trust_model=False)
    if owner is not None and owner.id != product.id:
        raise NameTaken(key, owner)

    if key == normalize_product_name(
        str(product.canonical_name)
    ) and not await _name_row(db, key):
        await learn_product_name(db, product, key, source=NameSource.CANONICAL)
        created = False
    else:
        created = await learn_product_name(db, product, key, source=NameSource.COOK)
    row: Any = await _name_row(db, key)
    if row.product_master_id != product.id:
        # Taught to another product after our check: learn_product_name left it alone.
        other = await crud_product.get_product(db, row.product_master_id)
        raise NameTaken(key, cast(ProductMaster, other))  # the row's FK: it exists

    taught = TaughtName(created=created, entry=_entry(row))
    if claim is not None:
        await idempotency.remember(
            db, claim, taught.status_code, taught.entry.model_dump(mode="json")
        )
    return taught


async def _name_row(db: AsyncSession, key: str) -> ProductName | None:
    return (
        (
            await db.execute(
                select(ProductName)
                .where(ProductName.name == key)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .first()
    )


async def teach_name(
    db: AsyncSession,
    product_id: UUID,
    name: str,
    *,
    claim: IdempotencyClaim | None = None,
) -> TaughtName:
    """Make ``name`` mean this product, as the cook's word, and commit.

    A name the product already has is left as it is (a model's guess for it becomes the
    cook's word, as `learn_product_name` does). So is its own canonical name when no
    `product_name` row records it yet (a product Open Food Facts wrote): the missing
    canonical row is filled in, which changes what no name means. A model's guess pointing
    at another product is re-pointed, again as `learn_product_name` does; a canonical or
    cook name of another product is refused - also when another request teaches it the
    name between this one's check and its write.

    Raises:
        ProductNotFound: No such product.
        NameTaken: The name already means another product.
    """
    key = normalize_product_name(name)
    try:
        try:
            taught = await _teach(db, product_id, key, claim)
        except IntegrityError:
            # Another request wrote this name after our check: look again, and it is
            # either another product's (NameTaken) or already ours (unchanged).
            await db.rollback()
            taught = await _teach(db, product_id, key, claim)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise

    logger.info(
        "Product name taught",
        extra={
            "product_id": str(product_id),
            "product_name": key,
            "name_created": taught.created,
        },
    )
    return taught
