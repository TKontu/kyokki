"""Identity is a key, not a score (H13, `docs/PRODUCT_RESOLUTION_SPEC.md`).

The table in spec §1 is the reason this service exists. Reproduced against the real
matcher with a catalog of Milk, Apple, Cream, Butter, Tomato, five of six lines resolved
wrongly *and confidently*:

    OATLY KAURAJUOMA   Oat milk       -> Milk    90 "high"
    PIRKKA ANANAS      Pineapple      -> Apple   90 "high"
    VALIO SMETANA      Sour cream     -> Cream   90 "high"
    MAAPÄHKINÄVOI      Peanut butter  -> Butter  90 "high"
    KIRSIKKATOMAATTI   Cherry tomato  -> Tomato  90 "high"
    ATRIA JAUHELIHA    Minced beef    -> none    64

Confirm then turned each mistake into a `manually_verified` alias that won for every
later receipt from that chain. These tests pin the new answers: nothing for the five,
and Ground beef for the sixth once a synonym exists.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import seed_categories
from app.models.category import Category
from app.models.product_master import ProductMaster
from app.models.store_product_alias import StoreProductAlias
from app.services.llm_extractor import LLMExtractionError
from app.services.product_names import learn_product_name
from app.services.product_resolution import (
    ProductResolution,
    ResolvableLine,
    TrigramRetriever,
)

CATEGORIES = [("dairy", 7), ("produce", 10), ("meat", 5)]

# The spec's table, as (printed, generic, category).
SUBSTRING_TRAPS = [
    ("OATLY KAURAJUOMA", "Oat milk", "dairy"),
    ("PIRKKA ANANAS", "Pineapple", "produce"),
    ("VALIO SMETANA", "Sour cream", "dairy"),
    ("MAAPÄHKINÄVOI", "Peanut butter", "pantry"),
    ("KIRSIKKATOMAATTI", "Cherry tomato", "produce"),
]


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    for order, (category_id, days) in enumerate(CATEGORIES):
        db_session.add(
            Category(
                id=category_id,
                display_name=category_id.title(),
                icon="*",
                default_shelf_life_days=days,
                sort_order=order,
            )
        )
    await db_session.commit()


async def _product(
    db: AsyncSession, name: str, category: str = "dairy"
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="count",
        default_unit="pcs",
    )
    db.add(product)
    await db.flush()
    await learn_product_name(db, product, name, "canonical")
    await db.commit()
    return product


@pytest.fixture
async def catalog(db_session: AsyncSession, categories) -> dict[str, ProductMaster]:
    return {
        "milk": await _product(db_session, "Milk", "dairy"),
        "apple": await _product(db_session, "Apple", "produce"),
        "cream": await _product(db_session, "Cream", "dairy"),
        "butter": await _product(db_session, "Butter", "dairy"),
        "tomato": await _product(db_session, "Tomato", "produce"),
        "beef": await _product(db_session, "Ground beef", "meat"),
    }


def _line(printed: str, generic: str | None = None, category: str | None = None):
    return ResolvableLine(
        line_id=printed, printed=printed, generic=generic, category=category
    )


class TestTheSpecTable:
    """No product id is ever assigned from a similarity score."""

    @pytest.mark.parametrize(("printed", "generic", "category"), SUBSTRING_TRAPS)
    async def test_a_substring_never_resolves(
        self, db_session: AsyncSession, catalog, printed, generic, category
    ) -> None:
        resolved = await ProductResolution(db_session).resolve(
            [_line(printed, generic, category)], chain="s-group"
        )

        result = resolved[printed]
        assert result.product is None
        assert result.source == "none"

    async def test_a_synonym_resolves_where_similarity_could_not(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """ "Minced beef" scores 64 against "Ground beef" - unreachable for any
        threshold that also tolerates OCR noise. One confirm teaches it.

        A synonym the model taught pre-fills the row but is not the cook's word, so it
        resolves unverified and the row shows it as "auto" (H51, Q13). Before that it
        was a key that won outright, which is how "ketchup" stayed Taco sauce for ever.
        """
        await learn_product_name(db_session, catalog["beef"], "Minced beef", "model")
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("ATRIA JAUHELIHA", "Minced beef", "meat")], chain="s-group"
        )

        result = resolved["ATRIA JAUHELIHA"]
        assert result.product is not None
        assert result.product.id == catalog["beef"].id
        assert (result.source, result.verified) == ("name", False)

    async def test_a_synonym_the_cook_taught_is_verified(
        self, db_session: AsyncSession, catalog
    ) -> None:
        await learn_product_name(db_session, catalog["beef"], "Minced beef", "cook")
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("ATRIA JAUHELIHA", "Minced beef", "meat")], chain="s-group"
        )

        result = resolved["ATRIA JAUHELIHA"]
        assert result.product is not None
        assert result.product.id == catalog["beef"].id
        assert (result.source, result.verified) == ("name", True)

    async def test_the_r1b_regression_holds_without_a_threshold(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """CHEDDAR PUNAINEN must not pair with PUNASIPULI. The old fix was a score
        floor of 80; there is no score here to floor."""
        await _product(db_session, "Punasipuli", "produce")

        resolved = await ProductResolution(db_session).resolve(
            [_line("CHEDDAR PUNAINEN", "Red cheddar", "dairy")], chain="s-group"
        )

        assert resolved["CHEDDAR PUNAINEN"].product is None


class TestDeterministicTiers:
    async def test_a_known_catalog_name_resolves_and_is_verified(
        self, db_session: AsyncSession, catalog
    ) -> None:
        resolved = await ProductResolution(db_session).resolve(
            [_line("VALIO MAITO", "Milk", "dairy")], chain="s-group"
        )

        result = resolved["VALIO MAITO"]
        assert result.product is not None and result.product.id == catalog["milk"].id
        assert (result.source, result.verified) == ("name", True)

    async def test_a_product_with_no_name_row_is_still_a_verified_key(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """Open Food Facts enrichment writes straight to `product_master`; a product's
        own name is the strongest key there is."""
        feta = ProductMaster(
            id=uuid4(),
            canonical_name="Feta",
            category="dairy",
            storage_type="refrigerator",
            default_shelf_life_days=7,
            unit_type="weight",
            default_unit="g",
        )
        db_session.add(feta)
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("COOP FETA PDO", "Feta", "dairy")], chain="s-group"
        )

        result = resolved["COOP FETA PDO"]
        assert result.product is not None and result.product.id == feta.id
        assert (result.source, result.verified) == ("name", True)

    async def test_an_alias_wins_over_everything_else(
        self, db_session: AsyncSession, catalog
    ) -> None:
        db_session.add(
            StoreProductAlias(
                product_master_id=catalog["cream"].id,
                store_chain="s-group",
                receipt_name="MILK",
                manually_verified=True,
                occurrence_count=3,
                last_seen=datetime.now(UTC),
            )
        )
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("MILK", "Milk", "dairy")], chain="s-group"
        )

        result = resolved["MILK"]
        assert result.product is not None and result.product.id == catalog["cream"].id
        assert (result.source, result.verified) == ("alias", True)

    async def test_an_unverified_alias_resolves_but_is_not_verified(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """It still pre-fills the row; the row shows it as "auto" rather than known."""
        db_session.add(
            StoreProductAlias(
                product_master_id=catalog["butter"].id,
                store_chain="s-group",
                receipt_name="VOI",
                manually_verified=False,
                occurrence_count=1,
                last_seen=datetime.now(UTC),
            )
        )
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("VOI")], chain="s-group"
        )

        assert resolved["VOI"].source == "alias"
        assert resolved["VOI"].verified is False

    async def test_the_cooks_own_alias_beats_a_machine_one(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """Precedence is verified, then occurrence count, then recency. Since H14 one
        printed name has at most one alias per chain, so this is decided between
        chains - here the receipt is from a third chain, so neither wins on chain."""
        now = datetime.now(UTC)
        db_session.add_all(
            [
                StoreProductAlias(
                    product_master_id=catalog["milk"].id,
                    store_chain="k-group",
                    receipt_name="X",
                    source="model",
                    manually_verified=False,
                    occurrence_count=9,
                    last_seen=now,
                ),
                StoreProductAlias(
                    product_master_id=catalog["cream"].id,
                    store_chain="lidl",
                    receipt_name="X",
                    source="cook",
                    manually_verified=True,
                    occurrence_count=1,
                    last_seen=now,
                ),
            ]
        )
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("X")], chain="s-group"
        )

        assert resolved["X"].product.id == catalog["cream"].id

    async def test_one_printed_name_has_one_alias_per_chain(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """Enforced only by a SELECT-then-insert in confirm before H14, so two
        concurrent confirms could duplicate the row."""
        now = datetime.now(UTC)
        db_session.add(
            StoreProductAlias(
                product_master_id=catalog["milk"].id,
                store_chain="s-group",
                receipt_name="X",
                source="cook",
                manually_verified=True,
                occurrence_count=1,
                last_seen=now,
            )
        )
        await db_session.flush()
        db_session.add(
            StoreProductAlias(
                product_master_id=catalog["cream"].id,
                store_chain="s-group",
                receipt_name="X",
                source="model",
                manually_verified=False,
                occurrence_count=1,
                last_seen=now,
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.flush()
        await db_session.rollback()

    async def test_this_chains_alias_beats_another_chains(
        self, db_session: AsyncSession, catalog
    ) -> None:
        now = datetime.now(UTC)
        db_session.add_all(
            [
                StoreProductAlias(
                    product_master_id=catalog["milk"].id,
                    store_chain="k-group",
                    receipt_name="Y",
                    manually_verified=True,
                    occurrence_count=9,
                    last_seen=now,
                ),
                StoreProductAlias(
                    product_master_id=catalog["cream"].id,
                    store_chain="s-group",
                    receipt_name="Y",
                    manually_verified=False,
                    occurrence_count=1,
                    last_seen=now,
                ),
            ]
        )
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("Y")], chain="s-group"
        )

        assert resolved["Y"].product.id == catalog["cream"].id

    async def test_a_remembered_non_food_line_stops_there(
        self, db_session: AsyncSession, catalog
    ) -> None:
        resolved = await ProductResolution(db_session).resolve(
            [_line("MUOVIKASSI")], chain="s-group", non_food={"MUOVIKASSI"}
        )

        assert resolved["MUOVIKASSI"].non_food is True
        assert resolved["MUOVIKASSI"].product is None


class TestSelection:
    """The model may only choose from what it was offered."""

    async def test_a_choice_from_the_shortlist_is_accepted(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        _no_model_selection.side_effect = lambda lines: {
            lines[0].line_id: catalog["milk"].id
        }

        resolved = await ProductResolution(db_session).resolve(
            [_line("KAURAJUOMA", "Oat drink", "dairy")], chain="s-group"
        )

        result = resolved["KAURAJUOMA"]
        assert result.product is not None and result.product.id == catalog["milk"].id
        assert (result.source, result.verified) == ("selected", False)

    async def test_the_shortlist_is_recorded_even_when_nothing_is_chosen(
        self, db_session: AsyncSession, catalog
    ) -> None:
        resolved = await ProductResolution(db_session).resolve(
            [_line("KAURAJUOMA", "Oat drink", "dairy")], chain="s-group"
        )

        assert resolved["KAURAJUOMA"].candidates != []

    async def test_a_model_that_cannot_be_reached_leaves_lines_unresolved(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """The receipt still completes. Nothing falls back to similarity - that is the
        whole point of the refactor."""
        _no_model_selection.side_effect = LLMExtractionError("gateway down")

        resolved = await ProductResolution(db_session).resolve(
            [_line("KAURAJUOMA", "Oat drink", "dairy")], chain="s-group"
        )

        assert resolved["KAURAJUOMA"].product is None
        assert resolved["KAURAJUOMA"].source == "none"

    async def test_the_model_is_not_asked_when_every_line_resolves(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """A warm catalog costs no model call at all."""
        await ProductResolution(db_session).resolve(
            [_line("VALIO MAITO", "Milk", "dairy")], chain="s-group"
        )

        _no_model_selection.assert_not_awaited()


class TestRetrieval:
    async def test_a_shortlist_includes_the_same_category(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """So "Oat milk" always sees every dairy product, however poor the trigram."""
        candidates = await TrigramRetriever(db_session).candidates(
            _line("KAURAJUOMA", "Oat drink", "dairy")
        )

        assert {c.name for c in candidates} >= {"Milk", "Cream", "Butter"}

    async def test_a_shortlist_is_bounded(
        self, db_session: AsyncSession, catalog
    ) -> None:
        candidates = await TrigramRetriever(db_session, limit=2).candidates(
            _line("KAURAJUOMA", "Oat drink", "dairy")
        )

        assert len(candidates) <= 2

    async def test_a_near_miss_is_shortlisted_by_trigram(
        self, db_session: AsyncSession, catalog
    ) -> None:
        """OCR noise is what similarity is still good for - as a shortlist, not a decision."""
        candidates = await TrigramRetriever(db_session).candidates(
            _line("GRUND BEEF", "Grund beef", None)
        )

        assert "Ground beef" in {c.name for c in candidates}


REPORTED_PAIRS = json.loads(
    (
        Path(__file__).parent.parent / "fixtures" / "resolution" / "reported_pairs.json"
    ).read_text(encoding="utf-8")
)["cases"]


@pytest.fixture
async def seeded(db_session: AsyncSession) -> None:
    await seed_categories(db_session)
    await db_session.commit()


async def _names(db: AsyncSession, line: ResolvableLine) -> list[str]:
    return [c.name for c in await TrigramRetriever(db).candidates(line)]


class TestAShortlistThatContainsTheAnswer:
    """H53 (Q14): the answer has to be on the shortlist before the model can pick it.

    Trigram over whole names missed Finnish compounds, and when it found fewer than five the
    rest were the category's products in alphabetical order - a fruits line saw Apple,
    Banana, Grape, Kiwi and Lime and never Melon.
    """

    @pytest.mark.parametrize(
        "case", [c for c in REPORTED_PAIRS if c["must_offer"]], ids=lambda c: c["id"]
    )
    async def test_each_reported_line_is_offered_its_product(
        self, db_session: AsyncSession, seeded, case
    ) -> None:
        for name, category in case["catalog"]:
            await _product(db_session, name, category)

        offered = await _names(
            db_session, _line(case["printed"], case["generic"], case["category"])
        )

        assert case["must_offer"] in offered

    async def test_the_category_competes_on_similarity_not_the_alphabet(
        self, db_session: AsyncSession, seeded
    ) -> None:
        for name in ("Apple", "Banana", "Grape", "Kiwi", "Lime", "Mango", "Melon"):
            await _product(db_session, name, "fruits")

        offered = await _names(db_session, _line("HUNAJAMELONI", "Honeydew", "fruits"))

        assert offered[0] == "Melon"

    async def test_a_whole_word_in_common_ranks_first(
        self, db_session: AsyncSession, seeded
    ) -> None:
        for name, category in (
            ("Taco sauce", "condiments"),
            ("Taco shells", "pantry"),
            ("Tortilla", "bread"),
        ):
            await _product(db_session, name, category)

        offered = await _names(
            db_session, _line("TACO SHELLS 12KPL", "Taco shells", "pantry")
        )

        assert offered[:2] == ["Taco shells", "Taco sauce"]

    async def test_a_shared_word_beats_near_misses(
        self, db_session: AsyncSession, seeded
    ) -> None:
        """Five names that merely look alike cannot push out one that shares a word."""
        for name in ("Peach", "Peanut", "Peas", "Pecan", "Pearl barley"):
            await _product(db_session, name, "pantry")
        await _product(db_session, "Pear", "fruits")

        offered = await _names(db_session, _line("PÄÄRYNÄ", "Pear", None))

        assert offered[0] == "Pear"

    async def test_a_product_with_no_name_row_is_found_by_its_own_name(
        self, db_session: AsyncSession, seeded
    ) -> None:
        """Open Food Facts enrichment writes straight to `product_master`."""
        db_session.add(
            ProductMaster(
                id=uuid4(),
                canonical_name="Melon",
                category="fruits",
                storage_type="refrigerator",
                default_shelf_life_days=7,
                unit_type="count",
                default_unit="pcs",
            )
        )
        await db_session.commit()

        offered = await _names(db_session, _line("HUNAJAMELONI", None, None))

        assert offered == ["Melon"]

    async def test_a_line_with_only_a_printed_name_still_works(
        self, db_session: AsyncSession, seeded
    ) -> None:
        await _product(db_session, "Ketchup", "condiments")

        offered = await _names(db_session, _line("KETCHUP", None, None))

        assert offered == ["Ketchup"]

    async def test_nothing_alike_and_no_category_offers_nothing(
        self, db_session: AsyncSession, seeded
    ) -> None:
        """An empty shortlist means no model call for the line (spec §3.3)."""
        await _product(db_session, "Ketchup", "condiments")

        assert await _names(db_session, _line("XYZZY", "Plumbus", None)) == []

    async def test_a_line_with_no_usable_words_does_not_break_the_query(
        self, db_session: AsyncSession, seeded
    ) -> None:
        await _product(db_session, "Ketchup", "condiments")

        assert await _names(db_session, _line("400G", None, None)) == []
