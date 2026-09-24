"""Deciding which product a receipt line is.

Replaces `MatchingService.match_line`. The rule that shapes everything here is the
spec's first principle: **identity is a key, not a score**
(`docs/PRODUCT_RESOLUTION_SPEC.md` §2).

Fuzzy similarity conflated containment with identity - "Sour cream" scored 90 against
"Cream", "Pineapple" 90 against "Apple" - and confirm turned each mistake into a
verified alias that won for ever. Similarity survives here in exactly one role:
building a shortlist for the model to choose from, which the model is good at and the
scorer never was.

Tiers, in order, stopping at the first hit:

1. a printed name the cook has already called non-food
2. an alias for (this chain, printed name)
3. an alias for (any chain, printed name)
4. a known catalog name for the generic name
5. a known catalog name for the printed name
6. otherwise unresolved - and only then, a shortlist and one model call per receipt

Nothing falls back to similarity. If the model is unreachable, unresolved lines stay
unresolved and the receipt still completes.

A name is verified when the catalog stands behind it: the product's own name or a word
the cook used. A synonym the model taught (`product_name.source = model`) still
resolves, but unverified, so the review row shows it as "auto" rather than "known"
(H51, Q13) and the cook's correction at confirm re-points it.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.product_master import ProductMaster
from app.models.product_name import ProductName
from app.models.store_product_alias import StoreProductAlias
from app.services.llm_extractor import LLMExtractionError
from app.services.matching_service import normalize_receipt_name
from app.services.product_names import known_names, normalize_product_name
from app.services.product_selection import SelectionLine, select_products

logger = get_logger(__name__)

ResolutionSource = Literal["alias", "name", "selected", "none"]

# Five is enough for a household catalog and keeps the selection prompt small.
CANDIDATES_PER_LINE = 5
# Below this trigram similarity a name is noise rather than a near miss.
TRIGRAM_FLOOR = 0.2


@dataclass(frozen=True)
class Candidate:
    product_id: UUID
    name: str

    def as_dict(self) -> dict[str, str]:
        return {"product_id": str(self.product_id), "name": self.name}


@dataclass(frozen=True)
class ResolvableLine:
    """What resolution needs to know about one receipt line."""

    line_id: str
    printed: str
    generic: str | None = None
    category: str | None = None


@dataclass
class Resolution:
    """How one line was resolved, and what it was offered if it was not."""

    product: ProductMaster | None = None
    source: ResolutionSource = "none"
    verified: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    non_food: bool = False
    # Where the alias itself came from, when `source` is "alias". Confirm reads it back
    # so reinforcing a mapping keeps its provenance instead of claiming the cook's word.
    alias_source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """The blob stored on the receipt line (H12 shape)."""
        blob: dict[str, Any] = {
            "product_id": str(self.product.id) if self.product else None,
            "source": self.source,
            "verified": self.verified,
            "candidates": [c.as_dict() for c in self.candidates],
        }
        if self.alias_source is not None:
            blob["alias_source"] = self.alias_source
        return blob


class TrigramRetriever:
    """Shortlists candidates with `pg_trgm`, plus everything in the line's category.

    Behind an interface on purpose: an embedding retriever (pgvector plus a model on
    the gateway) can replace this without resolution or the prompt changing. Not needed
    for a household-sized catalog (spec §3.3).
    """

    def __init__(self, db: AsyncSession, limit: int = CANDIDATES_PER_LINE):
        self.db = db
        self.limit = limit

    async def candidates(self, line: ResolvableLine) -> list[Candidate]:
        found: dict[UUID, Candidate] = {}

        for term in (line.generic, line.printed):
            key = normalize_product_name(term)
            if not key:
                continue
            rows = (
                await self.db.execute(
                    text(
                        """
                        SELECT pn.product_master_id AS pid,
                               pm.canonical_name     AS name,
                               similarity(pn.name, :q) AS sim
                        FROM product_name pn
                        JOIN product_master pm ON pm.id = pn.product_master_id
                        WHERE similarity(pn.name, :q) >= :floor
                        ORDER BY sim DESC
                        LIMIT :k
                        """
                    ),
                    {"q": key, "floor": TRIGRAM_FLOOR, "k": self.limit},
                )
            ).all()
            for pid, name, _ in rows:
                found.setdefault(pid, Candidate(product_id=pid, name=str(name)))

        # Same-category products, so "Oat milk" always sees every dairy product even
        # when the trigram score is poor (spec §3.3).
        if line.category and len(found) < self.limit:
            same_category = (
                (
                    await self.db.execute(
                        select(ProductMaster)
                        .where(ProductMaster.category == line.category)
                        .order_by(ProductMaster.canonical_name)
                        .limit(self.limit)
                    )
                )
                .scalars()
                .all()
            )
            for product in same_category:
                product_id = cast(UUID, product.id)
                found.setdefault(
                    product_id,
                    Candidate(product_id=product_id, name=str(product.canonical_name)),
                )

        return list(found.values())[: self.limit]


class ProductResolution:
    """Resolve a whole receipt at once."""

    def __init__(self, db: AsyncSession, retriever: TrigramRetriever | None = None):
        self.db = db
        self.retriever = retriever or TrigramRetriever(db)

    async def resolve(
        self,
        lines: Sequence[ResolvableLine],
        *,
        chain: str | None,
        non_food: Iterable[str] = (),
        allow_model: bool = True,
    ) -> dict[str, Resolution]:
        """Line id -> resolution, for every line given."""
        remembered = set(non_food)
        results: dict[str, Resolution] = {}

        aliases = await self._aliases_for(lines, chain)
        names = await known_names(
            self.db,
            [part for line in lines for part in (line.generic, line.printed) if part],
        )

        unresolved: list[ResolvableLine] = []
        for line in lines:
            printed_key = normalize_receipt_name(line.printed)
            if printed_key in remembered:
                results[line.line_id] = Resolution(non_food=True)
                continue

            alias = aliases.get(printed_key)
            if alias is not None:
                product = await self.db.get(ProductMaster, alias.product_master_id)
                if product is not None:
                    results[line.line_id] = Resolution(
                        product=product,
                        source="alias",
                        verified=bool(alias.manually_verified),
                        alias_source=str(alias.source or "cook"),
                    )
                    continue

            named = names.get(normalize_product_name(line.generic)) or names.get(
                normalize_product_name(line.printed)
            )
            if named is not None:
                # A catalog name is a key. The cook's catalog stands behind its own
                # names and the cook's words; a model's synonym only pre-fills (H51).
                results[line.line_id] = Resolution(
                    product=named.product,
                    source="name",
                    verified=named.source != "model",
                )
                continue

            results[line.line_id] = Resolution()
            unresolved.append(line)

        if unresolved and allow_model:
            await self._select(unresolved, results)

        return results

    async def _aliases_for(
        self, lines: Sequence[ResolvableLine], chain: str | None
    ) -> dict[str, StoreProductAlias]:
        """The best alias per printed name: this chain first, then any chain.

        Only the names on this receipt are fetched. The old matcher loaded every
        product and every alias in the database for each receipt.
        """
        keys = {normalize_receipt_name(line.printed) for line in lines}
        keys.discard("")
        if not keys:
            return {}

        rows = (
            (
                await self.db.execute(
                    select(StoreProductAlias).where(
                        StoreProductAlias.receipt_name.in_(keys)
                    )
                )
            )
            .scalars()
            .all()
        )

        def rank(alias: StoreProductAlias) -> tuple[int, int, int, Any]:
            """Same chain, then the cook's own word, then how often, then how recent."""
            return (
                1 if chain and str(alias.store_chain) == chain else 0,
                1 if alias.manually_verified else 0,
                int(alias.occurrence_count or 0),
                alias.last_seen,
            )

        best: dict[str, StoreProductAlias] = {}
        for alias in sorted(rows, key=rank):
            best[str(alias.receipt_name)] = alias  # last write wins: highest rank
        return best

    async def _select(
        self, unresolved: Sequence[ResolvableLine], results: dict[str, Resolution]
    ) -> None:
        """Shortlist each unresolved line, then ask the model once for the receipt."""
        askable: list[SelectionLine] = []
        for line in unresolved:
            candidates = await self.retriever.candidates(line)
            results[line.line_id].candidates = candidates
            if not candidates:
                continue
            askable.append(
                SelectionLine(
                    line_id=line.line_id,
                    printed=line.printed,
                    generic=line.generic,
                    category=line.category,
                    candidate_ids=tuple(str(c.product_id) for c in candidates),
                    candidate_names=tuple(c.name for c in candidates),
                )
            )

        if not askable:
            return

        try:
            chosen = await select_products(askable)
        except LLMExtractionError as exc:
            # The receipt still completes; these lines are simply new products. The one
            # thing that must not happen is a similarity guess taking their place.
            logger.warning(
                "Product selection unavailable; leaving lines unresolved",
                extra={"lines": len(askable), "error": str(exc)},
            )
            return

        for line_id, product_id in chosen.items():
            product = await self.db.get(ProductMaster, product_id)
            if product is None:
                continue
            results[line_id].product = product
            results[line_id].source = "selected"
            results[line_id].verified = False


async def canonical_names(db: AsyncSession, limit: int = 300) -> list[str]:
    """Catalog names offered to the extraction prompt for reuse.

    Still needed while the prompt carries the catalog; H17 measures dropping it.
    """
    rows = (
        (
            await db.execute(
                select(ProductMaster.canonical_name)
                .order_by(ProductMaster.canonical_name)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [str(name) for name in rows]


__all__ = [
    "Candidate",
    "ProductResolution",
    "Resolution",
    "ResolvableLine",
    "TrigramRetriever",
    "canonical_names",
    "ProductName",
]
