"""Product matching: receipt line names → canonical products.

Order of precedence (MVP-R1b):
1. Store alias, exact: a name learned for this store chain (then any chain) wins outright.
2. Canonical product name, exact (case and whitespace insensitive).
3. Fuzzy (RapidFuzz WRatio) over canonical names and alias names, so OCR-noise variants of a
   known receipt line still land on the right product.

``prepare()`` loads products and aliases once; ``match_line()`` then runs without queries.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.product_master import ProductMaster
from app.models.store_product_alias import StoreProductAlias

logger = get_logger(__name__)

MatchSource = Literal["alias", "exact", "fuzzy", "fuzzy_alias"]

_TRAILING_PRICE = re.compile(r"\s+-?\d+[,.]\d{2}(\s*€)?$")


class MatchConfidence(StrEnum):
    """Match confidence levels based on fuzzy match score."""

    EXACT = "exact"  # 100% match (case-insensitive)
    HIGH = "high"  # >= 75%
    MEDIUM = "medium"  # >= 60%
    LOW = "low"  # >= 50%


@dataclass
class MatchResult:
    """Result of a product matching operation."""

    product: ProductMaster
    score: float  # 0-100, higher is better
    confidence: MatchConfidence
    source: MatchSource = "fuzzy"


@dataclass(frozen=True)
class _Candidate:
    text: str
    product: ProductMaster
    is_alias: bool


def normalize_receipt_name(name: str) -> str:
    """Upper-case, collapse whitespace, drop a trailing price: the alias lookup key."""
    collapsed = " ".join(name.upper().split())
    return _TRAILING_PRICE.sub("", collapsed).strip()


class MatchingService:
    """Match receipt product names to canonical products."""

    EXACT_THRESHOLD = 100.0
    HIGH_THRESHOLD = 75.0
    MEDIUM_THRESHOLD = 60.0
    LOW_THRESHOLD = 50.0

    def __init__(self, db: AsyncSession):
        self.db = db
        self._products: list[ProductMaster] | None = None
        self._aliases: list[StoreProductAlias] = []

    async def prepare(self, store_chain: str | None = None) -> None:
        """Load the catalog (products and aliases) once for a batch of lines.

        ``store_chain`` is accepted for symmetry with ``match_line``; all aliases are loaded so
        a line can fall back to another chain's alias when this chain has none.
        """
        self._products = await self._get_all_products()
        result = await self.db.execute(select(StoreProductAlias))
        self._aliases = list(result.scalars().all())
        by_id = {p.id: p for p in self._products}
        # Keep only aliases whose product is loaded (FK guarantees it; guard anyway)
        self._aliases = [a for a in self._aliases if a.product_master_id in by_id]
        self._product_by_id = by_id

    @property
    def product_names(self) -> list[str]:
        """Canonical names of the prepared catalog (offered to extraction for reuse)."""
        if self._products is None:
            raise RuntimeError(
                "MatchingService.prepare() must be awaited before product_names"
            )
        return [str(p.canonical_name) for p in self._products]

    def match_line(
        self,
        product_name: str,
        store_chain: str | None = None,
        min_score: float = LOW_THRESHOLD,
        generic_name: str | None = None,
    ) -> MatchResult | None:
        """Best match for one receipt line. Requires ``prepare()``; runs no queries.

        ``generic_name`` is the brand-free name from extraction ("Ground beef"). Products are
        generic, so it reaches the product even when the printed name shares no words with it.
        A learned alias for the printed name still wins.
        """
        if self._products is None:
            raise RuntimeError(
                "MatchingService.prepare() must be awaited before match_line()"
            )

        name = product_name.strip()
        if not name or not self._products:
            return None

        key = normalize_receipt_name(name)

        alias = self._best_alias(key, store_chain)
        if alias is not None:
            return MatchResult(
                product=self._product_by_id[alias.product_master_id],
                score=100.0,
                confidence=MatchConfidence.EXACT,
                source="alias",
            )

        generic_key = normalize_receipt_name(generic_name) if generic_name else ""
        if generic_key:
            generic = self._exact_canonical(generic_key)
            if generic is not None:
                return MatchResult(
                    product=generic,
                    score=100.0,
                    confidence=MatchConfidence.EXACT,
                    source="exact",
                )

        exact = self._exact_canonical(key)
        if exact is not None:
            return MatchResult(
                product=exact,
                score=100.0,
                confidence=MatchConfidence.EXACT,
                source="exact",
            )

        candidates = self._candidates(store_chain)
        best = process.extractOne(
            key,
            [c.text for c in candidates],
            scorer=fuzz.WRatio,
            processor=str.upper,
            score_cutoff=min_score,
        )
        generic_best = None
        if generic_key:
            # Generic names are compared with product names only: aliases are printed names
            generic_best = process.extractOne(
                generic_key,
                [str(p.canonical_name) for p in self._products],
                scorer=fuzz.WRatio,
                processor=str.upper,
                score_cutoff=min_score,
            )
        if generic_best and (not best or generic_best[1] > best[1]):
            _, score, index = generic_best
            return MatchResult(
                product=self._products[index],
                score=float(score),
                confidence=self._calculate_confidence(score),
                source="fuzzy",
            )
        if not best:
            return None
        _, score, index = best
        candidate = candidates[index]
        return MatchResult(
            product=candidate.product,
            score=float(score),
            confidence=self._calculate_confidence(score),
            source="fuzzy_alias" if candidate.is_alias else "fuzzy",
        )

    async def match_product(
        self,
        product_name: str,
        min_score: float = LOW_THRESHOLD,
    ) -> MatchResult | None:
        """Match a single name without a store context (loads the catalog each call)."""
        await self.prepare(None)
        return self.match_line(product_name, None, min_score=min_score)

    async def match_all(
        self,
        product_name: str,
        limit: int = 5,
        min_score: float = LOW_THRESHOLD,
    ) -> list[MatchResult]:
        """Top matches by canonical name, best first. Same-named products stay distinct."""
        name = product_name.strip()
        if not name:
            return []
        products = await self._get_all_products()
        if not products:
            return []

        results = process.extract(
            name,
            [str(p.canonical_name) for p in products],
            scorer=fuzz.WRatio,
            processor=str.upper,
            score_cutoff=min_score,
            limit=limit,
        )
        return [
            MatchResult(
                product=products[index],
                score=float(score),
                confidence=self._calculate_confidence(score),
                source="exact" if score >= self.EXACT_THRESHOLD else "fuzzy",
            )
            for _, score, index in results
        ]

    def _best_alias(
        self, key: str, store_chain: str | None
    ) -> StoreProductAlias | None:
        matches = [
            a
            for a in self._aliases
            if normalize_receipt_name(str(a.receipt_name)) == key
        ]
        if not matches:
            return None
        same_chain = [
            a for a in matches if store_chain and a.store_chain == store_chain
        ]
        pool = same_chain or matches
        return max(
            pool, key=lambda a: (bool(a.manually_verified), a.occurrence_count or 0)
        )

    def _exact_canonical(self, key: str) -> ProductMaster | None:
        assert self._products is not None
        for product in self._products:
            if normalize_receipt_name(str(product.canonical_name)) == key:
                return product
        return None

    def _candidates(self, store_chain: str | None) -> list[_Candidate]:
        assert self._products is not None
        candidates = [
            _Candidate(text=str(p.canonical_name), product=p, is_alias=False)
            for p in self._products
        ]
        aliases = self._aliases
        if store_chain:
            # Prefer this chain's receipt names; other chains' names still help when absent
            aliases = sorted(aliases, key=lambda a: a.store_chain != store_chain)
        candidates.extend(
            _Candidate(
                text=str(a.receipt_name),
                product=self._product_by_id[a.product_master_id],
                is_alias=True,
            )
            for a in aliases
        )
        return candidates

    async def _get_all_products(self) -> list[ProductMaster]:
        result = await self.db.execute(select(ProductMaster))
        return list(result.scalars().all())

    def _calculate_confidence(self, score: float) -> MatchConfidence:
        if score >= self.EXACT_THRESHOLD:
            return MatchConfidence.EXACT
        if score >= self.HIGH_THRESHOLD:
            return MatchConfidence.HIGH
        if score >= self.MEDIUM_THRESHOLD:
            return MatchConfidence.MEDIUM
        return MatchConfidence.LOW
