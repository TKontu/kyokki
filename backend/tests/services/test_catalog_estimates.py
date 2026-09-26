"""The catalog asking the model about itself (Q11).

Q7 fixed why the model stopped estimating shelf lives, and Q11's `shelf_life_source`
made a placeholder replaceable. Neither repairs what is already stored: on the homelab
46 of 50 products carried their category's blanket figure and 45 of them had never been
estimated at all, because the receipts that created them predate `sl`.

The risk being managed here is not "the model is wrong sometimes" - it is that this
writes to the whole catalog in one go, so an answer that is confident and absurd has to
be dropped rather than stored.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_categories import SEED_CATEGORIES
from app.services.catalog_estimates import (
    INSTRUCTIONS,
    Estimate,
    EstimateRequest,
    band_for,
    build_prompt,
    estimate_products,
    parse_estimates,
    refresh_catalog_shelf_lives,
)
from app.services.generic_products import ProductResolver
from app.services.llm_extractor import LLMExtractionError


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


# The produce placeholder these products are created with; read from the seed so a revised
# placeholder (H57) does not read as a behaviour change.
PRODUCE_DAYS = next(
    c["default_shelf_life_days"] for c in SEED_CATEGORIES if c["id"] == "produce"
)

MINCE = EstimateRequest(id="p-mince", name="Ground beef", category="meat")
PASTA = EstimateRequest(id="p-pasta", name="Pasta", category="pantry")


def _answer(rows: str) -> str:
    return '{"r": [' + rows + "]}"


class TestBuildPrompt:
    def test_it_carries_the_name_and_category_of_every_product(self) -> None:
        prompt = build_prompt([MINCE, PASTA])

        assert "Ground beef" in prompt
        assert "Pasta" in prompt
        assert "p-mince" in prompt

    def test_it_never_sends_a_shelf_life(self) -> None:
        """The model is asked what a thing keeps for, not to review a stored number.

        Offering the current value invites agreement with it, and the current value is
        exactly the placeholder this is trying to replace.
        """
        prompt = build_prompt([MINCE])

        assert "5" not in prompt.split("Products:")[1]


class TestTheKitchenAnchors:
    """Q19: the examples the model calibrates against are the operator's own numbers.

    The old examples (mince 2, banana 7) taught the model a fridge nobody has: most of a
    fresh shop went red two days after it was bought.
    """

    @pytest.mark.parametrize(
        "example",
        [
            "packed minced beef -> d 5",
            "meat from the butcher's counter -> d 3",
            "fresh fish -> d 3",
            "banana -> d 5",
            "tomato -> d 14",
            "orange -> d 21",
            "sliced ham -> d 10, o 5",
            "salami -> d 30, o 14",
            "hard cheese -> d 60, o 21",
            "milk -> d 7, o 5",
            "rye crispbread -> d 720, o 60",
            "dried pasta -> d 720",
            "onion -> d 30",
        ],
    )
    def test_every_anchor_is_in_the_prompt(self, example: str) -> None:
        assert example in " ".join(INSTRUCTIONS.split())

    def test_the_old_short_numbers_are_gone(self) -> None:
        flat = " ".join(INSTRUCTIONS.split())

        assert "minced beef -> d 2;" not in flat
        assert "banana -> d 7" not in flat

    def test_it_counts_from_the_day_of_purchase_for_a_finnish_supermarket(self) -> None:
        flat = " ".join(INSTRUCTIONS.split())

        assert "from the day of purchase" in flat
        assert "Finnish supermarket" in flat

    @pytest.mark.parametrize(
        "category, days",
        [
            ("meat", 5),
            ("meat", 3),
            ("fish", 3),
            ("fruits", 5),
            ("produce", 14),
            ("fruits", 21),
        ],
    )
    def test_every_anchor_is_inside_its_band(self, category: str, days: int) -> None:
        low, high = band_for(category)

        assert low <= days <= high


class TestParseEstimates:
    def test_it_reads_a_plain_answer(self) -> None:
        estimates = parse_estimates(
            _answer('{"id": "p-mince", "d": 2, "o": null}'), [MINCE]
        )

        assert estimates == [
            Estimate(id="p-mince", shelf_life_days=2, opened_shelf_life_days=None)
        ]

    def test_it_reads_an_opened_shelf_life(self) -> None:
        (estimate,) = parse_estimates(
            _answer('{"id": "p-pasta", "d": 720, "o": 60}'), [PASTA]
        )

        assert (estimate.shelf_life_days, estimate.opened_shelf_life_days) == (720, 60)

    def test_it_unwraps_a_reasoning_block(self) -> None:
        """muse-glimmer is a reasoning model; `extract_json_object` is shared for this."""
        content = "<think>mince goes off fast</think>" + _answer(
            '{"id": "p-mince", "d": 2}'
        )

        assert parse_estimates(content, [MINCE])[0].shelf_life_days == 2

    @pytest.mark.parametrize("days", [400, 0, -3, None, "soon"])
    def test_it_drops_an_implausible_or_unusable_number(self, days) -> None:
        """400 days of mince is a confident wrong answer, and this writes to 45 rows.

        A dropped answer is not a failure: the product keeps the placeholder it had.
        """
        content = _answer(json.dumps({"id": "p-mince", "d": days}))

        assert parse_estimates(content, [MINCE]) == []

    def test_a_number_plausible_for_one_category_may_be_absurd_for_another(
        self,
    ) -> None:
        """720 days is right for pasta and nonsense for mince, so the band is per category."""
        assert parse_estimates(_answer('{"id": "p-pasta", "d": 720}'), [PASTA])
        assert parse_estimates(_answer('{"id": "p-mince", "d": 720}'), [MINCE]) == []

    def test_an_opened_life_longer_than_the_sealed_one_is_dropped(self) -> None:
        """Opening something cannot make it last longer; keep the half it got right."""
        (estimate,) = parse_estimates(
            _answer('{"id": "p-mince", "d": 2, "o": 30}'), [MINCE]
        )

        assert (estimate.shelf_life_days, estimate.opened_shelf_life_days) == (2, None)

    def test_it_ignores_a_product_it_was_not_asked_about(self) -> None:
        """The discipline `parse_selection` applies to identity, applied to a number."""
        content = _answer('{"id": "p-invented", "d": 9}, {"id": "p-mince", "d": 2}')

        assert [e.id for e in parse_estimates(content, [MINCE])] == ["p-mince"]

    def test_it_keeps_the_first_answer_for_a_repeated_product(self) -> None:
        content = _answer('{"id": "p-mince", "d": 2}, {"id": "p-mince", "d": 40}')

        assert [e.shelf_life_days for e in parse_estimates(content, [MINCE])] == [2]

    def test_an_answer_with_no_result_list_is_unusable(self) -> None:
        with pytest.raises(LLMExtractionError):
            parse_estimates('{"nope": true}', [MINCE])


class TestRefreshCatalogShelfLives:
    """The write path. Nothing here may touch a number the cook chose."""

    async def _product(self, db_session: AsyncSession, name: str, **kwargs):
        product, _ = await ProductResolver(db_session).resolve(
            name=name, category="produce", unit="pcs", quantity=1, **kwargs
        )
        return product

    def _says(self, *estimates: Estimate):
        return patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            return_value=list(estimates),
        )

    async def test_a_dry_run_proposes_without_writing(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await self._product(db_session, "Ground beef")
        assert product.default_shelf_life_days == PRODUCE_DAYS

        with self._says(
            Estimate(id=str(product.id), shelf_life_days=2, opened_shelf_life_days=None)
        ):
            result = await refresh_catalog_shelf_lives(db_session, apply=False)

        assert result.applied is False
        assert [(c.current_days, c.proposed_days) for c in result.changes] == [
            (PRODUCE_DAYS, 2)
        ]
        assert product.default_shelf_life_days == PRODUCE_DAYS  # untouched

    async def test_applying_writes_the_number_and_its_provenance(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await self._product(db_session, "Ground beef")

        with self._says(
            Estimate(id=str(product.id), shelf_life_days=2, opened_shelf_life_days=None)
        ):
            result = await refresh_catalog_shelf_lives(db_session, apply=True)

        assert result.applied is True
        assert product.default_shelf_life_days == 2
        # ...and it is now an answer, so the next refresh leaves it alone
        assert product.shelf_life_source == "model"

    async def test_a_number_the_cook_chose_is_never_even_offered(
        self, db_session: AsyncSession, categories
    ) -> None:
        """The whole safety property. A batch job may not argue with a correction."""
        product = await self._product(db_session, "Ground beef")
        product.default_shelf_life_days = 2
        product.shelf_life_source = "cook"
        await db_session.flush()

        asked: list[list[EstimateRequest]] = []

        async def capture(products):
            asked.append(products)
            return []

        with patch("app.services.catalog_estimates.estimate_shelf_lives", new=capture):
            result = await refresh_catalog_shelf_lives(db_session, apply=True)

        assert result.considered == 0
        assert asked == []  # not even a request was built
        assert product.default_shelf_life_days == 2

    async def test_a_product_the_model_already_estimated_is_left_alone(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await self._product(db_session, "Pasta", shelf_life_days=720)
        assert product.shelf_life_source == "model"

        result = await refresh_catalog_shelf_lives(db_session, apply=True)

        assert result.considered == 0

    async def test_an_unchanged_number_is_not_a_change(
        self, db_session: AsyncSession, categories
    ) -> None:
        """The model agreeing with the category is a real outcome, not a correction."""
        product = await self._product(db_session, "Lettuce")

        with self._says(
            Estimate(
                id=str(product.id),
                shelf_life_days=PRODUCE_DAYS,
                opened_shelf_life_days=None,
            )
        ):
            result = await refresh_catalog_shelf_lives(db_session, apply=True)

        assert result.answered == 1
        assert result.changes == []

    async def test_an_opened_shelf_life_is_filled_but_never_rewritten(
        self, db_session: AsyncSession, categories
    ) -> None:
        filled = await self._product(db_session, "Ham")
        known = await self._product(db_session, "Sour cream", opened_shelf_life_days=5)

        with self._says(
            Estimate(id=str(filled.id), shelf_life_days=10, opened_shelf_life_days=4),
            Estimate(id=str(known.id), shelf_life_days=14, opened_shelf_life_days=99),
        ):
            await refresh_catalog_shelf_lives(db_session, apply=True)

        assert filled.opened_shelf_life_days == 4
        assert known.opened_shelf_life_days == 5

    async def test_an_empty_catalog_asks_nothing(
        self, db_session: AsyncSession, categories
    ) -> None:
        result = await refresh_catalog_shelf_lives(db_session, apply=True)

        assert (result.considered, result.answered, result.changes) == (0, 0, [])


class TestEstimateProducts:
    """Q19: one function estimates and applies any list of products, with one rule.

    The catalog refresh, re-estimating everything and the estimate a new product gets all go
    through it, so what may change is decided in one place: never a `cook` number, and an
    opened shelf life only when it is missing.
    """

    async def _product(self, db_session: AsyncSession, name: str, **kwargs):
        product, _ = await ProductResolver(db_session).resolve(
            name=name, category="produce", unit="pcs", quantity=1, **kwargs
        )
        return product

    def _says(self, days: int, opened: int | None = None):
        async def answer(products):
            return [
                Estimate(id=p.id, shelf_life_days=days, opened_shelf_life_days=opened)
                for p in products
            ]

        return patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new=AsyncMock(side_effect=answer),
        )

    async def test_it_replaces_a_placeholder_and_a_model_value(
        self, db_session: AsyncSession, categories
    ) -> None:
        placeholder = await self._product(db_session, "Tomato")
        guessed = await self._product(db_session, "Orange", shelf_life_days=7)

        with self._says(21):
            result = await estimate_products(
                db_session, [placeholder, guessed], apply=True
            )

        assert result.considered == 2
        assert (
            placeholder.default_shelf_life_days,
            guessed.default_shelf_life_days,
        ) == (
            21,
            21,
        )
        assert {placeholder.shelf_life_source, guessed.shelf_life_source} == {"model"}

    async def test_a_cook_number_is_never_sent(
        self, db_session: AsyncSession, categories
    ) -> None:
        cooks = await self._product(db_session, "Tomato")
        cooks.default_shelf_life_days = 4
        cooks.shelf_life_source = "cook"
        other = await self._product(db_session, "Carrot")

        with self._says(21) as estimator:
            result = await estimate_products(db_session, [cooks, other], apply=True)

        (asked,) = estimator.await_args.args
        assert [r.id for r in asked] == [str(other.id)]
        assert result.considered == 1
        assert (cooks.default_shelf_life_days, cooks.shelf_life_source) == (4, "cook")

    async def test_an_answer_that_agrees_still_marks_it_answered(
        self, db_session: AsyncSession, categories
    ) -> None:
        """Otherwise a placeholder the model agreed with would be asked about for ever."""
        product = await self._product(db_session, "Lettuce")

        with self._says(PRODUCE_DAYS):
            result = await estimate_products(db_session, [product], apply=True)

        assert result.changes == []
        assert product.shelf_life_source == "model"

    async def test_a_dry_run_marks_nothing(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await self._product(db_session, "Lettuce")

        with self._says(PRODUCE_DAYS):
            await estimate_products(db_session, [product], apply=False)

        assert product.shelf_life_source == "category"


class TestRefreshScope:
    """Q19: `scope="all"` re-estimates every product the cook has not set."""

    async def _catalog(self, db_session: AsyncSession):
        placeholder, _ = await ProductResolver(db_session).resolve(
            name="Tomato", category="produce", unit="pcs", quantity=1
        )
        guessed, _ = await ProductResolver(db_session).resolve(
            name="Orange", category="produce", unit="pcs", quantity=1, shelf_life_days=7
        )
        cooks, _ = await ProductResolver(db_session).resolve(
            name="Banana", category="produce", unit="pcs", quantity=1
        )
        cooks.default_shelf_life_days = 5
        cooks.shelf_life_source = "cook"
        await db_session.flush()
        return placeholder, guessed, cooks

    async def _asked(self, db_session: AsyncSession, **kwargs) -> list[str]:
        asked: list[str] = []

        async def capture(products):
            asked.extend(p.name for p in products)
            return []

        with patch("app.services.catalog_estimates.estimate_shelf_lives", new=capture):
            await refresh_catalog_shelf_lives(db_session, **kwargs)
        return sorted(asked)

    async def test_guesses_is_the_default_and_asks_only_about_placeholders(
        self, db_session: AsyncSession, categories
    ) -> None:
        await self._catalog(db_session)

        assert await self._asked(db_session) == ["Tomato"]
        assert await self._asked(db_session, scope="guesses") == ["Tomato"]

    async def test_all_asks_about_everything_but_the_cooks(
        self, db_session: AsyncSession, categories
    ) -> None:
        await self._catalog(db_session)

        assert await self._asked(db_session, scope="all") == ["Orange", "Tomato"]

    async def test_all_is_still_a_dry_run_by_default(
        self, db_session: AsyncSession, categories
    ) -> None:
        placeholder, guessed, _ = await self._catalog(db_session)

        with patch(
            "app.services.catalog_estimates.estimate_shelf_lives",
            new_callable=AsyncMock,
            return_value=[
                Estimate(
                    id=str(guessed.id), shelf_life_days=21, opened_shelf_life_days=None
                )
            ],
        ):
            result = await refresh_catalog_shelf_lives(db_session, scope="all")

        assert result.applied is False
        assert [c.proposed_days for c in result.changes] == [21]
        assert guessed.default_shelf_life_days == 7

    async def test_an_unknown_scope_is_refused(
        self, db_session: AsyncSession, categories
    ) -> None:
        with pytest.raises(ValueError):
            await refresh_catalog_shelf_lives(db_session, scope="everything")


class TestPlausibleBands:
    def test_every_seeded_category_has_its_own_band(self) -> None:
        """H55: a new category must not fall through to the loose default band."""
        from app.db.seed_categories import SEED_CATEGORIES
        from app.services.catalog_estimates import PLAUSIBLE_DAYS

        assert {c["id"] for c in SEED_CATEGORIES} <= set(PLAUSIBLE_DAYS)

    def test_a_ready_meal_does_not_keep_for_months(self) -> None:
        from app.services.catalog_estimates import PLAUSIBLE_DAYS

        low, high = PLAUSIBLE_DAYS["ready_meals"]
        assert low >= 1
        assert high <= 30

    def test_every_placeholder_is_itself_plausible(self) -> None:
        """H57: a seed default outside its own band would be a number the estimate rejects."""
        from app.db.seed_categories import SEED_CATEGORIES
        from app.services.catalog_estimates import PLAUSIBLE_DAYS

        for category in SEED_CATEGORIES:
            low, high = PLAUSIBLE_DAYS[category["id"]]
            assert low <= category["default_shelf_life_days"] <= high, category["id"]
