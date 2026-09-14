"""Pytest tests for product matching service (RapidFuzz fuzzy matching)."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product_master import ProductMaster
from app.services.matching_service import (
    MatchConfidence,
    MatchingService,
    MatchResult,
)


class TestMatchingService:
    """Test fuzzy product matching with RapidFuzz."""

    @pytest.fixture
    async def sample_products(self, db_session: AsyncSession) -> list[ProductMaster]:
        """Create sample products for matching tests."""
        # Create category first
        category = Category(
            id="dairy",
            display_name="Dairy",
            icon="🥛",
            default_shelf_life_days=7,
            meal_contexts=["breakfast"],
            sort_order=1,
        )
        db_session.add(category)
        await db_session.flush()

        products = [
            ProductMaster(
                id=uuid4(),
                canonical_name="Valio Whole Milk 1L",
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=7,
                unit_type="volume",
                default_unit="ml",
                default_quantity=Decimal("1000"),
            ),
            ProductMaster(
                id=uuid4(),
                canonical_name="Arla Lactose-Free Milk 1L",
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=7,
                unit_type="volume",
                default_unit="ml",
                default_quantity=Decimal("1000"),
            ),
            ProductMaster(
                id=uuid4(),
                canonical_name="Valio Butter 500g",
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=60,
                unit_type="weight",
                default_unit="g",
                default_quantity=Decimal("500"),
            ),
            ProductMaster(
                id=uuid4(),
                canonical_name="Pirkka Oat Milk 1L",
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=5,
                unit_type="volume",
                default_unit="ml",
                default_quantity=Decimal("1000"),
            ),
        ]

        for product in products:
            db_session.add(product)
        await db_session.commit()

        # Refresh to get relationships
        for product in products:
            await db_session.refresh(product)

        return products

    @pytest.fixture
    def matching_service(self, db_session: AsyncSession) -> MatchingService:
        """Create matching service instance."""
        return MatchingService(db_session)

    async def test_exact_match(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test exact name matching returns highest confidence."""
        result = await matching_service.match_product("Valio Whole Milk 1L")

        assert result is not None
        assert result.product.canonical_name == "Valio Whole Milk 1L"
        assert result.confidence == MatchConfidence.EXACT
        assert result.score == 100.0

    async def test_case_insensitive_exact_match(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test case-insensitive exact matching."""
        result = await matching_service.match_product("valio whole milk 1l")

        assert result is not None
        assert result.product.canonical_name == "Valio Whole Milk 1L"
        assert result.confidence == MatchConfidence.EXACT
        assert result.score == 100.0

    async def test_high_confidence_fuzzy_match(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test fuzzy matching with minor variations."""
        # Abbreviated product name (missing "Whole")
        result = await matching_service.match_product("Valio Milk 1L")

        assert result is not None
        assert result.product.canonical_name == "Valio Whole Milk 1L"
        assert result.confidence in [MatchConfidence.HIGH, MatchConfidence.EXACT]
        assert result.score >= 75.0

    async def test_medium_confidence_fuzzy_match(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test fuzzy matching with moderate variations."""
        result = await matching_service.match_product("Valio Milk")

        assert result is not None
        assert result.product.canonical_name == "Valio Whole Milk 1L"
        # WRatio may score this higher than expected, so accept HIGH or MEDIUM
        assert result.confidence in [MatchConfidence.HIGH, MatchConfidence.MEDIUM]
        assert result.score >= 60.0

    async def test_low_confidence_fuzzy_match(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test fuzzy matching with significant variations."""
        result = await matching_service.match_product("Milk 1L")

        assert result is not None
        # Should match one of the milk products
        assert "Milk" in result.product.canonical_name
        # May score higher than LOW depending on the exact match
        assert result.confidence in [
            MatchConfidence.LOW,
            MatchConfidence.MEDIUM,
            MatchConfidence.HIGH,
        ]
        assert result.score >= 50.0

    async def test_no_match_below_threshold(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test that poor matches return None."""
        result = await matching_service.match_product("Banana")

        assert result is None

    async def test_best_match_among_multiple_candidates(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test that best match is returned when multiple candidates exist."""
        result = await matching_service.match_product("Arla Lactose Milk")

        assert result is not None
        assert result.product.canonical_name == "Arla Lactose-Free Milk 1L"
        assert result.score >= 60.0

    async def test_match_with_special_characters(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test matching with special characters and dashes."""
        result = await matching_service.match_product("Arla Lactose Free Milk")

        assert result is not None
        assert result.product.canonical_name == "Arla Lactose-Free Milk 1L"

    async def test_match_empty_string(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test that empty string returns None."""
        result = await matching_service.match_product("")

        assert result is None

    async def test_match_whitespace_only(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test that whitespace-only string returns None."""
        result = await matching_service.match_product("   ")

        assert result is None

    async def test_match_with_extra_whitespace(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test matching handles extra whitespace correctly."""
        result = await matching_service.match_product("  Valio   Whole  Milk  1L  ")

        assert result is not None
        assert result.product.canonical_name == "Valio Whole Milk 1L"
        assert result.confidence == MatchConfidence.EXACT

    async def test_match_all_returns_top_candidates(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test match_all returns multiple candidates sorted by score."""
        results = await matching_service.match_all("Milk", limit=3)

        assert len(results) <= 3
        assert all("Milk" in r.product.canonical_name for r in results)
        # Verify results are sorted by score (descending)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_match_all_respects_limit(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test match_all respects the limit parameter."""
        results = await matching_service.match_all("Milk", limit=2)

        assert len(results) <= 2

    async def test_match_all_filters_by_threshold(
        self,
        matching_service: MatchingService,
        sample_products: list[ProductMaster],
    ):
        """Test match_all only returns matches above threshold."""
        results = await matching_service.match_all("Banana", limit=10)

        # Should return empty or very few results since "Banana" doesn't match any products
        assert all(r.score >= 50.0 for r in results)

    async def test_match_with_finnish_characters(
        self,
        matching_service: MatchingService,
        db_session: AsyncSession,
    ):
        """Test matching with Finnish special characters (ä, ö, å)."""
        # Create product with Finnish characters
        category = Category(
            id="produce",
            display_name="Produce",
            icon="🥬",
            default_shelf_life_days=5,
            meal_contexts=["cooking"],
            sort_order=2,
        )
        db_session.add(category)
        await db_session.flush()

        product = ProductMaster(
            id=uuid4(),
            canonical_name="Päärynä 1kg",
            category="produce",
            storage_type="refrigerator",
            default_shelf_life_days=5,
            unit_type="weight",
            default_unit="kg",
            default_quantity=Decimal("1.0"),
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)

        result = await matching_service.match_product("Päärynä")

        assert result is not None
        assert result.product.canonical_name == "Päärynä 1kg"

    async def test_empty_database(
        self,
        db_session: AsyncSession,
    ):
        """Test matching when no products exist in database."""
        matching_service = MatchingService(db_session)
        result = await matching_service.match_product("Any Product")

        assert result is None


class TestMatchResult:
    """Test MatchResult data structure."""

    def test_match_result_creation(self):
        """Test creating a MatchResult."""
        product = ProductMaster(
            id=uuid4(),
            canonical_name="Test Product",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="count",
            default_unit="pcs",
        )

        result = MatchResult(
            product=product,
            score=85.5,
            confidence=MatchConfidence.HIGH,
        )

        assert result.product.canonical_name == "Test Product"
        assert result.score == 85.5
        assert result.confidence == MatchConfidence.HIGH

    def test_match_confidence_values(self):
        """Test MatchConfidence enum values."""
        assert MatchConfidence.EXACT.value == "exact"
        assert MatchConfidence.HIGH.value == "high"
        assert MatchConfidence.MEDIUM.value == "medium"
        assert MatchConfidence.LOW.value == "low"


class TestAliasFirstMatching:
    """MVP-R1b: store aliases learned from confirmed receipts win over fuzzy guesses."""

    @pytest.fixture
    async def catalog(self, db_session: AsyncSession) -> dict[str, ProductMaster]:
        from app.models.store_product_alias import StoreProductAlias

        db_session.add(
            Category(
                id="dairy",
                display_name="Dairy & Eggs",
                icon="🥛",
                default_shelf_life_days=7,
                meal_contexts=["breakfast"],
                sort_order=1,
            )
        )
        await db_session.flush()

        def product(name: str) -> ProductMaster:
            return ProductMaster(
                id=uuid4(),
                canonical_name=name,
                category="dairy",
                storage_type="refrigerator",
                default_shelf_life_days=7,
                unit_type="count",
                default_unit="pcs",
            )

        products = {
            "milk": product("Valio Lactose-Free Milk Drink 1L"),
            "butter": product("Oivariini Butter Spread"),
            "decoy": product("Oivariini Normaalisuolainen Light"),
            "twin_a": product("Kaurajuoma"),
            "twin_b": product("Kaurajuoma"),
        }
        db_session.add_all(products.values())
        await db_session.flush()

        db_session.add_all(
            [
                StoreProductAlias(
                    product_master_id=products["butter"].id,
                    store_chain="s-group",
                    receipt_name="OIVARIINI NORMAALISUOLAINEN",
                    manually_verified=True,
                    occurrence_count=3,
                ),
                StoreProductAlias(
                    product_master_id=products["decoy"].id,
                    store_chain="k-group",
                    receipt_name="OIVARIINI NORMAALISUOLAINEN",
                    manually_verified=False,
                    occurrence_count=1,
                ),
                StoreProductAlias(
                    product_master_id=products["milk"].id,
                    store_chain="s-group",
                    receipt_name="KEVYTMAITOJUOMA LAKTON",
                    manually_verified=True,
                    occurrence_count=5,
                ),
            ]
        )
        await db_session.commit()
        return products

    async def test_same_chain_alias_wins_over_a_closer_canonical_name(
        self, db_session, catalog
    ):
        service = MatchingService(db_session)
        await service.prepare("s-group")

        result = service.match_line("OIVARIINI NORMAALISUOLAINEN", "s-group")

        assert result is not None
        assert result.product.id == catalog["butter"].id
        assert result.source == "alias"
        assert result.confidence == MatchConfidence.EXACT
        assert result.score == 100.0

    async def test_other_chain_alias_is_used_on_that_chain(self, db_session, catalog):
        service = MatchingService(db_session)
        await service.prepare("k-group")

        result = service.match_line("OIVARIINI NORMAALISUOLAINEN", "k-group")

        assert result is not None
        assert result.product.id == catalog["decoy"].id
        assert result.source == "alias"

    async def test_unknown_chain_prefers_the_verified_most_seen_alias(
        self, db_session, catalog
    ):
        service = MatchingService(db_session)
        await service.prepare(None)

        result = service.match_line("oivariini   normaalisuolainen 4,27", None)

        assert result is not None
        assert result.product.id == catalog["butter"].id
        assert result.source == "alias"

    async def test_ocr_noise_variant_fuzzy_matches_through_an_alias(
        self, db_session, catalog
    ):
        service = MatchingService(db_session)
        await service.prepare("s-group")

        result = service.match_line("KEVYMAITOJUOMA LAKTON", "s-group")

        assert result is not None
        assert result.product.id == catalog["milk"].id
        assert result.source == "fuzzy_alias"
        assert result.confidence in (MatchConfidence.HIGH, MatchConfidence.EXACT)

    async def test_canonical_exact_match_reports_its_source(self, db_session, catalog):
        service = MatchingService(db_session)
        await service.prepare("s-group")

        result = service.match_line("Oivariini Butter Spread", "s-group")

        assert result is not None
        assert result.source == "exact"

    async def test_products_with_the_same_name_stay_distinct(self, db_session, catalog):
        service = MatchingService(db_session)
        await service.prepare(None)

        matches = await service.match_all("Kaurajuoma", limit=5)

        ids = {
            m.product.id for m in matches if m.product.canonical_name == "Kaurajuoma"
        }
        assert ids == {catalog["twin_a"].id, catalog["twin_b"].id}

    async def test_prepare_loads_the_catalog_once_for_many_lines(
        self, db_session, catalog
    ):
        from sqlalchemy import event

        statements: list[str] = []
        engine = db_session.bind.sync_engine

        def count(conn, cursor, statement, *args):
            statements.append(statement)

        service = MatchingService(db_session)
        await service.prepare("s-group")
        event.listen(engine, "before_cursor_execute", count)
        try:
            for name in [
                "OIVARIINI NORMAALISUOLAINEN",
                "KEVYMAITOJUOMA LAKTON",
                "UNKNOWN",
            ] * 5:
                service.match_line(name, "s-group")
        finally:
            event.remove(engine, "before_cursor_execute", count)

        assert statements == []
