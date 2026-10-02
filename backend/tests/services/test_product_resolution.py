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
    CANDIDATES_PER_LINE,
    Candidate,
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
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """ "Minced beef" scores 64 against "Ground beef" - unreachable for any
        threshold that also tolerates OCR noise. One confirm teaches it.

        A synonym the model taught pre-fills the row but is not the cook's word (H51,
        Q13): before that it was a key that won outright, which is how "ketchup" stayed
        Taco sauce for ever. Q37 went further - a model-taught synonym on the generic
        name is reached only through the model's own guess, so it is only ever a
        candidate, judged by selection like any other snap, not handed out unverified.
        """
        await learn_product_name(db_session, catalog["beef"], "Minced beef", "model")
        await db_session.commit()
        _no_model_selection.side_effect = lambda lines: {
            lines[0].line_id: catalog["beef"].id
        }

        resolved = await ProductResolution(db_session).resolve(
            [_line("ATRIA JAUHELIHA", "Minced beef", "meat")], chain="s-group"
        )

        result = resolved["ATRIA JAUHELIHA"]
        assert result.product is not None
        assert result.product.id == catalog["beef"].id
        assert (result.source, result.verified) == ("selected", False)

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
    async def test_a_known_catalog_name_resolves_only_through_selection(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """Q37: a catalog-name hit reached only through the model's generic name is a
        proposal, not a key - even a correct one like this must still be judged against
        the printed line, so it costs one model call rather than being final outright."""
        _no_model_selection.side_effect = lambda lines: {
            lines[0].line_id: catalog["milk"].id
        }

        resolved = await ProductResolution(db_session).resolve(
            [_line("VALIO MAITO", "Milk", "dairy")], chain="s-group"
        )

        result = resolved["VALIO MAITO"]
        assert result.product is not None and result.product.id == catalog["milk"].id
        assert (result.source, result.verified) == ("selected", False)
        _no_model_selection.assert_awaited_once()

    async def test_a_product_with_no_name_row_still_needs_selection_via_generic(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """Open Food Facts enrichment writes straight to `product_master`, so this is
        the canonical-name fallback, not a `product_name` row - but it was still reached
        only through the generic name, so it is a proposal like any other (Q37)."""
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
        _no_model_selection.side_effect = lambda lines: {lines[0].line_id: feta.id}

        resolved = await ProductResolution(db_session).resolve(
            [_line("COOP FETA PDO", "Feta", "dairy")], chain="s-group"
        )

        result = resolved["COOP FETA PDO"]
        assert result.product is not None and result.product.id == feta.id
        assert (result.source, result.verified) == ("selected", False)

    async def test_printed_name_hit_on_a_catalog_name_still_stays_deterministic(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """A catalog-name hit on the *printed* line is still a key: it is the receipt
        itself saying the product's own name, not the model's guess (Q37)."""
        resolved = await ProductResolution(db_session).resolve(
            [_line("Milk", "Oat drink", "dairy")], chain="s-group"
        )

        result = resolved["Milk"]
        assert result.product is not None and result.product.id == catalog["milk"].id
        assert (result.source, result.verified) == ("name", True)
        _no_model_selection.assert_not_awaited()

    async def test_a_generic_name_the_cook_taught_still_stays_deterministic(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """The cook's own word for a generic name - not merely the model's guess -
        stays a key, same as any other cook-taught synonym (Q37)."""
        await learn_product_name(db_session, catalog["beef"], "Mince", "cook")
        await db_session.commit()

        resolved = await ProductResolution(db_session).resolve(
            [_line("ATRIA JAUHELIHA", "Mince", "meat")], chain="s-group"
        )

        result = resolved["ATRIA JAUHELIHA"]
        assert result.product is not None and result.product.id == catalog["beef"].id
        assert (result.source, result.verified) == ("name", True)
        _no_model_selection.assert_not_awaited()

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


class TestGenericNameSnapping:
    """Q37: a catalog name reached only through the model's `g` is a proposal, never a
    final match, however it was learned - the product's own name (`canonical`) or a
    synonym the model itself taught (`model`). Pesto, cashew nuts, baking chocolate,
    butter, turkey cold cuts and chicken mince all snapped to an existing catalog entry
    this way on the Lidl receipt (`tests/fixtures/receipts/lidl_espoo_q37.txt`)."""

    async def test_the_snap_is_offered_but_not_final_on_its_own(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """Before the model is even asked, the snapped catalog product must already be
        a candidate - the whole point is that the printed line gets a second look, not
        that it is lost."""
        resolved = await ProductResolution(db_session).resolve(
            [_line("ALESTO SELECTION CASHEWP", "Butter", "pantry")], chain="s-group"
        )

        result = resolved["ALESTO SELECTION CASHEWP"]
        assert result.product is None
        assert result.source == "none"
        assert catalog["butter"].id in {c.product_id for c in result.candidates}

    async def test_the_model_rejects_the_snap_and_the_line_stays_unmatched(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """The model sees the printed line and answers null: a wrong pick is worse than
        none, and no duplicate of Butter gets created from this line."""
        _no_model_selection.side_effect = lambda lines: {}

        resolved = await ProductResolution(db_session).resolve(
            [_line("ALESTO SELECTION CASHEWP", "Butter", "pantry")], chain="s-group"
        )

        result = resolved["ALESTO SELECTION CASHEWP"]
        assert result.product is None
        assert result.source == "none"

    async def test_the_model_may_still_confirm_a_correct_snap(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """Mozzarella, farfalle and olive genuinely are the catalog entry their `g`
        names - selection, asked, says so, and the line resolves through it."""
        _no_model_selection.side_effect = lambda lines: {
            lines[0].line_id: catalog["milk"].id
        }

        resolved = await ProductResolution(db_session).resolve(
            [_line("VALIO KEVYTMAITO", "Milk", "dairy")], chain="s-group"
        )

        result = resolved["VALIO KEVYTMAITO"]
        assert result.product is not None and result.product.id == catalog["milk"].id
        assert (result.source, result.verified) == ("selected", False)

    async def test_a_model_taught_synonym_is_also_only_a_proposal(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """Not just the product's own (canonical) name: a synonym the model itself
        taught earlier (because the cook did not act on that line) is exactly as
        unreliable as a fresh snap and must be judged the same way."""
        await learn_product_name(db_session, catalog["butter"], "Dairy spread", "model")
        await db_session.commit()
        _no_model_selection.side_effect = lambda lines: {}

        resolved = await ProductResolution(db_session).resolve(
            [_line("OIVARIINI", "Dairy spread", "dairy")], chain="s-group"
        )

        result = resolved["OIVARIINI"]
        assert result.product is None
        assert result.source == "none"
        _no_model_selection.assert_awaited_once()


class _FixedRetriever:
    """A retriever stub: `candidates()` always returns this fixed list, in order,
    independent of the line or the database - for pinning exactly what the trigram
    shortlist handed `_select` before the snap is merged in (F2, F7)."""

    def __init__(self, fixed: list[Candidate]) -> None:
        self.fixed = fixed

    async def candidates(self, line: ResolvableLine) -> list[Candidate]:
        return list(self.fixed)


class TestSnapShortlistDiscipline:
    """PR #143 review, F2 and F7: the guaranteed slot for a snapped catalog name must
    not grow the shortlist past `CANDIDATES_PER_LINE`, and - having no trigram score of
    its own - must not sit first and bias selection towards it."""

    async def test_the_snap_does_not_push_the_shortlist_past_the_cap(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """F2: a full trigram shortlist plus the guaranteed snap would be six; the
        weakest trigram hit (last in the fixed list) gives way, not an arbitrary one."""
        trigram_hits = [
            Candidate(product_id=catalog["milk"].id, name="Milk"),
            Candidate(product_id=catalog["apple"].id, name="Apple"),
            Candidate(product_id=catalog["cream"].id, name="Cream"),
            Candidate(product_id=catalog["tomato"].id, name="Tomato"),
            Candidate(product_id=catalog["beef"].id, name="Ground beef"),
        ]
        assert len(trigram_hits) == CANDIDATES_PER_LINE

        resolved = await ProductResolution(
            db_session, retriever=_FixedRetriever(trigram_hits)
        ).resolve(
            [_line("ALESTO SELECTION CASHEWP", "Butter", "pantry")], chain="s-group"
        )

        candidates = resolved["ALESTO SELECTION CASHEWP"].candidates
        assert len(candidates) == CANDIDATES_PER_LINE
        ids = [c.product_id for c in candidates]
        assert catalog["butter"].id in ids
        assert catalog["beef"].id not in ids

    async def test_the_snap_is_placed_last_not_first(
        self, db_session: AsyncSession, catalog, _no_model_selection
    ) -> None:
        """F7: it has no trigram score of its own, so it must not sit ahead of hits
        that do, where a model reads shortlist order as a ranking."""
        trigram_hits = [
            Candidate(product_id=catalog["milk"].id, name="Milk"),
            Candidate(product_id=catalog["apple"].id, name="Apple"),
        ]

        resolved = await ProductResolution(
            db_session, retriever=_FixedRetriever(trigram_hits)
        ).resolve(
            [_line("ALESTO SELECTION CASHEWP", "Butter", "pantry")], chain="s-group"
        )

        candidates = resolved["ALESTO SELECTION CASHEWP"].candidates
        assert [c.product_id for c in candidates] == [
            catalog["milk"].id,
            catalog["apple"].id,
            catalog["butter"].id,
        ]


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
        """A warm catalog that resolves everything by printed name or alias costs no
        model call at all (Q37): a generic-name hit alone no longer counts as warm."""
        await ProductResolution(db_session).resolve(
            [_line("Milk", "Oat drink", "dairy")], chain="s-group"
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
