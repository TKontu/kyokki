"""Product matching service using RapidFuzz for fuzzy string matching.

Matches extracted receipt product names to canonical products in product_master.
"""
from enum import Enum
from dataclasses import dataclass
from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_master import ProductMaster
from app.core.logging import get_logger

logger = get_logger(__name__)


class MatchConfidence(str, Enum):
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


class MatchingService:
    """Service for matching receipt product names to canonical products.

    Uses RapidFuzz for fuzzy string matching with configurable thresholds.
    """

    # Matching thresholds
    EXACT_THRESHOLD = 100.0
    HIGH_THRESHOLD = 75.0
    MEDIUM_THRESHOLD = 60.0
    LOW_THRESHOLD = 50.0

    def __init__(self, db: AsyncSession):
        """Initialize matching service.

        Args:
            db: Database session for querying products.
        """
        self.db = db

    async def match_product(
        self,
        product_name: str,
        min_score: float = LOW_THRESHOLD,
    ) -> MatchResult | None:
        """Match a product name to the best canonical product.

        Uses fuzzy matching to find the most similar product in the database.
        Returns None if no match above the minimum score threshold is found.

        Args:
            product_name: Product name from receipt (any language/format).
            min_score: Minimum match score (0-100) to consider valid.

        Returns:
            MatchResult with best match, or None if no match above threshold.
        """
        # Normalize input
        product_name = product_name.strip()
        if not product_name:
            logger.debug("Empty product name provided")
            return None

        # Get all products from database
        products = await self._get_all_products()
        if not products:
            logger.debug("No products in database")
            return None

        # Check for exact match first (case-insensitive, normalized whitespace)
        product_name_normalized = " ".join(product_name.lower().split())
        for product in products:
            canonical_normalized = " ".join(product.canonical_name.lower().split())
            if canonical_normalized == product_name_normalized:
                logger.info(
                    f"Exact match found: '{product_name}' -> '{product.canonical_name}'"
                )
                return MatchResult(
                    product=product,
                    score=100.0,
                    confidence=MatchConfidence.EXACT,
                )

        # Extract product names for fuzzy matching
        product_names = [p.canonical_name for p in products]
        product_map = {p.canonical_name: p for p in products}

        # Find best match using RapidFuzz
        # Use WRatio for better matching with different word orders and partial matches
        result = process.extractOne(
            product_name,
            product_names,
            scorer=fuzz.WRatio,
            score_cutoff=min_score,
        )

        if not result:
            logger.debug(
                f"No match found for '{product_name}' above threshold {min_score}"
            )
            return None

        matched_name, score, _ = result
        matched_product = product_map[matched_name]
        confidence = self._calculate_confidence(score)

        logger.info(
            f"Matched '{product_name}' to '{matched_name}' "
            f"(score: {score:.1f}, confidence: {confidence.value})"
        )

        return MatchResult(
            product=matched_product,
            score=score,
            confidence=confidence,
        )

    async def match_all(
        self,
        product_name: str,
        limit: int = 5,
        min_score: float = LOW_THRESHOLD,
    ) -> list[MatchResult]:
        """Match a product name to multiple candidates.

        Returns top N matches sorted by score (descending).

        Args:
            product_name: Product name from receipt.
            limit: Maximum number of results to return.
            min_score: Minimum match score to consider valid.

        Returns:
            List of MatchResults sorted by score (best first).
        """
        # Normalize input
        product_name = product_name.strip()
        if not product_name:
            return []

        # Get all products from database
        products = await self._get_all_products()
        if not products:
            return []

        # Extract product names for matching
        product_names = [p.canonical_name for p in products]
        product_map = {p.canonical_name: p for p in products}

        # Find top matches using RapidFuzz
        # Use WRatio for better matching with different word orders and partial matches
        results = process.extract(
            product_name,
            product_names,
            scorer=fuzz.WRatio,
            score_cutoff=min_score,
            limit=limit,
        )

        # Convert to MatchResult objects
        match_results = []
        for matched_name, score, _ in results:
            matched_product = product_map[matched_name]
            confidence = self._calculate_confidence(score)
            match_results.append(
                MatchResult(
                    product=matched_product,
                    score=score,
                    confidence=confidence,
                )
            )

        logger.info(
            f"Found {len(match_results)} matches for '{product_name}' "
            f"(limit: {limit}, min_score: {min_score})"
        )

        return match_results

    async def _get_all_products(self) -> list[ProductMaster]:
        """Fetch all products from database.

        Returns:
            List of all ProductMaster instances.
        """
        stmt = select(ProductMaster)
        result = await self.db.execute(stmt)
        products = result.scalars().all()
        return list(products)

    def _calculate_confidence(self, score: float) -> MatchConfidence:
        """Calculate confidence level from match score.

        Args:
            score: Match score (0-100).

        Returns:
            Confidence level enum.
        """
        if score >= self.EXACT_THRESHOLD:
            return MatchConfidence.EXACT
        elif score >= self.HIGH_THRESHOLD:
            return MatchConfidence.HIGH
        elif score >= self.MEDIUM_THRESHOLD:
            return MatchConfidence.MEDIUM
        else:
            return MatchConfidence.LOW
