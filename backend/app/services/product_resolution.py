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
4. a known catalog name for the printed name
5. a known catalog name for the generic name, but only when it is the cook's own word
   for it (`product_name.source = cook`)
6. otherwise unresolved - and only then, a shortlist and one model call per receipt,
   which also carries any catalog name found only through the generic name (tier 7)

Nothing falls back to similarity. If the model is unreachable, unresolved lines stay
unresolved and the receipt still completes.

A name is verified when the catalog stands behind it: the product's own name, or a word
the cook used, matched on the printed line itself or taught as the cook's own synonym. A
hit on the generic name alone is never that: it is the model's guess at what the receipt
says, catalog-shaped or not, and Q37 is exactly this guess landing on an unrelated
catalog entry because the extraction prompt offers listed names too loosely ("Spread"
for butter, "Dip" for pesto and cashew nuts). So a catalog name reached only through the
generic name - whether it is the product's own (`canonical`) name or a synonym the model
itself taught earlier (`model`) - is carried into the shortlist as a candidate rather
than trusted outright: the line still goes to selection, which judges it against the
printed text with the same "same shopping-list line" rule as everything else, and a
`null` answer leaves the line unmatched rather than wrongly confirmed.
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
    # Q37b: the g-only snap selection said no to, and the better name it gave instead -
    # recorded only for the proposed (g-only) candidate, never a key or alias rejection.
    # Confirm reads `rejected_product_id` back so the line can never re-attach it
    # without the cook explicitly choosing it.
    rejected_product_id: UUID | None = None
    corrected_generic: str | None = None

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
        if self.rejected_product_id is not None:
            blob["rejected_product_id"] = str(self.rejected_product_id)
        if self.corrected_generic is not None:
            blob["corrected_generic"] = self.corrected_generic
        return blob


class TrigramRetriever:
    """The shortlist for a line: the products most like it, ranked over the whole catalog.

    Every product competes on the same score (H53, Q14):

    1. a whole word in common with one of its names ("taco shells" and Taco shells), which
       is why a shared word is always offered unless more than ``limit`` products share one;
    2. then trigram similarity - the better of whole-name and word similarity, so "melon"
       is found inside the Finnish compound "hunajameloni";
    3. then being in the line's category, which only breaks ties.

    This replaced trigram over names with the rest of the slots filled by the category in
    alphabetical order, which showed a fruits line Apple, Banana, Grape, Kiwi and Lime and
    never Melon. A product with no ``product_name`` row is ranked by its canonical name,
    the same fallback `known_names` uses.

    It scans the catalog, which is right for a household's few hundred products; the GIN
    index was never usable for a ``similarity() >= floor`` filter in any case.
    """

    def __init__(self, db: AsyncSession, limit: int = CANDIDATES_PER_LINE):
        self.db = db
        self.limit = limit

    async def candidates(self, line: ResolvableLine) -> list[Candidate]:
        generic = normalize_product_name(line.generic)
        printed = normalize_product_name(line.printed)
        if not generic and not printed:
            return []
        words = sorted(
            {
                word
                for word in f"{generic} {printed}".split()
                if len(word) >= 3 and word.isalpha()
            }
        )

        rows = (
            await self.db.execute(
                text(
                    """
                    WITH keys AS (
                        SELECT pn.product_master_id AS pid, pn.name AS key
                        FROM product_name pn
                        UNION ALL
                        SELECT pm.id, lower(btrim(pm.canonical_name))
                        FROM product_master pm
                    ),
                    scored AS (
                        SELECT k.pid,
                               bool_or(string_to_array(k.key, ' ') && :words) AS hit,
                               max(greatest(
                                   similarity(k.key, :g), similarity(k.key, :p),
                                   word_similarity(k.key, :g), word_similarity(:g, k.key),
                                   word_similarity(k.key, :p), word_similarity(:p, k.key)
                               )) AS sim
                        FROM keys k
                        GROUP BY k.pid
                    )
                    SELECT pm.id, pm.canonical_name
                    FROM scored s
                    JOIN product_master pm ON pm.id = s.pid
                    WHERE s.hit OR s.sim >= :floor OR pm.category = :c
                    ORDER BY s.hit DESC, s.sim DESC,
                             (pm.category = :c) DESC, pm.canonical_name
                    LIMIT :k
                    """
                ),
                {
                    # An empty term scores 0 rather than matching everything; NULL
                    # would make the whole greatest() NULL.
                    "g": generic or printed,
                    "p": printed or generic,
                    "words": words,
                    "c": line.category or "",
                    "floor": TRIGRAM_FLOOR,
                    "k": self.limit,
                },
            )
        ).all()
        return [Candidate(product_id=pid, name=str(name)) for pid, name in rows]


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
        # A catalog name found only through the model's generic name is a proposal, not
        # a key (Q37): carried here so `_select` can guarantee it is among that line's
        # candidates, even if the shortlist would not otherwise surface it.
        proposed: dict[str, ProductMaster] = {}
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

            # The receipt's own printed line naming a catalog product is a key: the
            # shop's text, not the model's guess (Q37).
            named_printed = names.get(normalize_product_name(line.printed))
            if named_printed is not None:
                results[line.line_id] = Resolution(
                    product=named_printed.product,
                    source="name",
                    verified=named_printed.source != "model",
                )
                continue

            named_generic = names.get(normalize_product_name(line.generic))
            if named_generic is not None and named_generic.source == "cook":
                # The cook's own word for this generic name - taught by typing it, not
                # merely left unchanged - is as reliable as any other cook key.
                results[line.line_id] = Resolution(
                    product=named_generic.product, source="name", verified=True
                )
                continue

            results[line.line_id] = Resolution()
            if named_generic is not None:
                # Reached only through `g`, whether the product's own name
                # (`canonical`) or a synonym the model itself taught (`model`): offer
                # it, do not hand it out (Q37).
                proposed[line.line_id] = named_generic.product
            unresolved.append(line)

        if unresolved and allow_model:
            await self._select(unresolved, results, proposed)

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
        self,
        unresolved: Sequence[ResolvableLine],
        results: dict[str, Resolution],
        proposed: dict[str, ProductMaster] | None = None,
    ) -> None:
        """Shortlist each unresolved line, then ask the model once for the receipt.

        ``proposed`` is the snapped catalog product for a line whose only hit was
        through the generic name (Q37): guaranteed a candidate slot even when the
        trigram shortlist would not otherwise surface it, so the printed line always
        gets a real look at the name the model proposed before it is confirmed or let go.
        Added last, not first - it has no trigram score of its own, so it must not read
        as the ranked top choice - and never past ``CANDIDATES_PER_LINE`` (review F2,
        F7): the weakest trigram hit gives way rather than the offer running long.
        """
        proposed = proposed or {}
        askable: list[SelectionLine] = []
        for line in unresolved:
            candidates = await self.retriever.candidates(line)
            snap = proposed.get(line.line_id)
            if snap is not None:
                snap_id = cast(UUID, snap.id)
                if not any(c.product_id == snap_id for c in candidates):
                    # It has no trigram score of its own, so it goes last rather than
                    # first, where a model reads shortlist order as a ranking (F7); and
                    # it must not grow the offer past the cap, so the weakest trigram
                    # hit gives way rather than the shortlist running long (F2).
                    if len(candidates) >= CANDIDATES_PER_LINE:
                        candidates = candidates[: CANDIDATES_PER_LINE - 1]
                    candidates = [
                        *candidates,
                        Candidate(product_id=snap_id, name=str(snap.canonical_name)),
                    ]
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
            answer = await select_products(askable)
        except LLMExtractionError as exc:
            # The receipt still completes; these lines are simply new products. The one
            # thing that must not happen is a similarity guess taking their place.
            logger.warning(
                "Product selection unavailable; leaving lines unresolved",
                extra={"lines": len(askable), "error": str(exc)},
            )
            return

        # `answer` is ordinarily a `SelectionResult`, but a test double may still hand
        # back a plain `dict[str, UUID]` (the shape every caller used before Q37b), so
        # the chosen products are read as a dict either way and `.corrected` is read
        # only when present.
        chosen: dict[str, UUID] = dict(answer)
        corrected: dict[str, str] = dict(getattr(answer, "corrected", None) or {})

        for line_id, product_id in chosen.items():
            product = await self.db.get(ProductMaster, product_id)
            if product is None:
                continue
            results[line_id].product = product
            results[line_id].source = "selected"
            results[line_id].verified = False

        # A rejection exists only for the g-only proposal (Q37b): a line whose snap was
        # offered but whose answer did not land on it - a trigram-only line that stayed
        # unmatched never proposed anything, so there is nothing to have rejected.
        for line_id, snap in proposed.items():
            if line_id in chosen:
                continue
            results[line_id].rejected_product_id = cast(UUID, snap.id)
            name = corrected.get(line_id)
            if name:
                results[line_id].corrected_generic = name


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
