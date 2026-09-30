"""Q18 build: applying the curated emoji table to the existing catalog.

`backfill_emoji.py` walks the whole catalog once, sets the curated table's answer (or a
confirmed proposal already learned) with no model call, and skips non-food, `cook` and
`cleared` products entirely - a hand-set choice, or one the cook cleared, is never overwritten.
`--propose` also asks the model, batched, for the names neither table knows.
"""

from uuid import uuid4

import pytest
from scripts import backfill_emoji
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product_master import EmojiMatch, ProductMaster
from app.services.non_food import remember_non_food


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


async def _product(
    db: AsyncSession,
    name: str,
    *,
    category: str = "cheese",
    emoji: str | None = None,
    emoji_match: EmojiMatch | None = None,
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
        emoji=emoji,
        emoji_match=emoji_match.value if emoji_match else None,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _reload(db: AsyncSession, product: ProductMaster) -> ProductMaster:
    return await db.get(ProductMaster, product.id, populate_existing=True)  # type: ignore[return-value]


class TestPlan:
    async def test_a_ruled_exact_product_is_planned(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")

        changes = await backfill_emoji.plan(db_session, propose=False)

        (change,) = [c for c in changes if c.id == product.id]
        assert change.emoji == "🧀"
        assert change.match == EmojiMatch.EXACT

    async def test_a_gap_product_is_planned_as_none(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Mozzarella")

        changes = await backfill_emoji.plan(db_session, propose=False)

        (change,) = [c for c in changes if c.id == product.id]
        assert change.emoji is None
        assert change.match == EmojiMatch.NONE

    async def test_a_settled_product_is_not_replanned(
        self, db_session: AsyncSession, categories
    ) -> None:
        await _product(db_session, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT)

        changes = await backfill_emoji.plan(db_session, propose=False)

        assert changes == []

    async def test_non_food_is_skipped(
        self, db_session: AsyncSession, categories
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        product = await _product(db_session, "Toilet paper", category="pantry")

        changes = await backfill_emoji.plan(db_session, propose=False)

        assert product.id not in {c.id for c in changes}

    async def test_cook_is_never_touched(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(
            db_session, "Gouda", emoji="🥨", emoji_match=EmojiMatch.COOK
        )

        changes = await backfill_emoji.plan(db_session, propose=False)

        assert product.id not in {c.id for c in changes}

    async def test_cleared_is_never_touched(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda", emoji_match=EmojiMatch.CLEARED)

        changes = await backfill_emoji.plan(db_session, propose=False)

        assert product.id not in {c.id for c in changes}

    async def test_an_unknown_name_is_left_alone_without_propose(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(
            db_session, "A Brand New Kind Of Snack", category="snacks"
        )

        changes = await backfill_emoji.plan(db_session, propose=False)

        assert product.id not in {c.id for c in changes}

    async def test_propose_asks_the_model_only_for_misses(
        self, db_session: AsyncSession, categories, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        known = await _product(db_session, "Gouda")
        miss = await _product(
            db_session, "A Brand New Kind Of Snack", category="snacks"
        )
        seen_names = []

        async def fake_propose(names, **kwargs):
            seen_names.extend(names)
            from app.services.product_emoji import ProposalAnswer

            return [ProposalAnswer("🥨", EmojiMatch.PROPOSED) for _ in names]

        monkeypatch.setattr(backfill_emoji.product_emoji, "propose", fake_propose)

        changes = await backfill_emoji.plan(db_session, propose=True)

        assert seen_names == ["A Brand New Kind Of Snack"]
        (change,) = [c for c in changes if c.id == miss.id]
        assert change.emoji == "🥨"
        assert change.match == EmojiMatch.PROPOSED
        assert known.id in {c.id for c in changes}  # the table hit is still planned


class TestApplyChanges:
    async def test_it_writes_every_planned_change(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        changes = await backfill_emoji.plan(db_session, propose=False)

        applied = await backfill_emoji.apply_changes(db_session, changes)

        assert applied == len(changes)
        stored = await _reload(db_session, product)
        assert stored.emoji == "🧀"
        assert stored.emoji_match == EmojiMatch.EXACT

    async def test_a_cook_choice_made_meanwhile_is_not_overwritten(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        changes = await backfill_emoji.plan(db_session, propose=False)
        # The cook got there first, after the plan was read but before it was applied.
        product.emoji = "🥨"
        product.emoji_match = EmojiMatch.COOK.value
        await db_session.commit()

        await backfill_emoji.apply_changes(db_session, changes)

        stored = await _reload(db_session, product)
        assert stored.emoji == "🥨"
        assert stored.emoji_match == EmojiMatch.COOK


class TestBackfillDryRunVsReal:
    async def test_dry_run_prints_but_writes_nothing(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        product = await _product(db_session, "Gouda")

        await backfill_emoji.backfill(
            dry_run=True, propose=False, sessions=session_factory
        )

        stored = await _reload(db_session, product)
        assert stored.emoji is None
        assert stored.emoji_match is None
        assert "would set" in capsys.readouterr().out

    async def test_a_real_run_applies_the_table_to_the_whole_catalog(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exact = await _product(db_session, "Gouda")
        gap = await _product(db_session, "Mozzarella")
        untouched_cook = await _product(
            db_session,
            "Custom",
            category="snacks",
            emoji="🥨",
            emoji_match=EmojiMatch.COOK,
        )
        untouched_cleared = await _product(
            db_session, "Cleared One", category="snacks", emoji_match=EmojiMatch.CLEARED
        )
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        non_food = await _product(db_session, "Toilet paper", category="pantry")

        await backfill_emoji.backfill(
            dry_run=False, propose=False, sessions=session_factory
        )

        assert (await _reload(db_session, exact)).emoji_match == EmojiMatch.EXACT
        assert (await _reload(db_session, exact)).emoji == "🧀"
        assert (await _reload(db_session, gap)).emoji_match == EmojiMatch.NONE
        assert (await _reload(db_session, gap)).emoji is None
        assert (
            await _reload(db_session, untouched_cook)
        ).emoji_match == EmojiMatch.COOK
        assert (await _reload(db_session, untouched_cook)).emoji == "🥨"
        assert (
            await _reload(db_session, untouched_cleared)
        ).emoji_match == EmojiMatch.CLEARED
        assert (await _reload(db_session, non_food)).emoji_match is None
        assert "applied" in capsys.readouterr().out


def test_main_parses_dry_run_and_propose(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    async def fake_backfill(
        *, dry_run, propose, sessions=backfill_emoji._default_sessions
    ):
        seen["dry_run"] = dry_run
        seen["propose"] = propose
        return []

    monkeypatch.setattr(backfill_emoji, "backfill", fake_backfill)

    code = backfill_emoji.main(["--dry-run", "--propose"])

    assert code == 0
    assert seen == {"dry_run": True, "propose": True}


def test_main_defaults_to_a_real_non_proposing_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    async def fake_backfill(
        *, dry_run, propose, sessions=backfill_emoji._default_sessions
    ):
        seen["dry_run"] = dry_run
        seen["propose"] = propose
        return []

    monkeypatch.setattr(backfill_emoji, "backfill", fake_backfill)

    code = backfill_emoji.main([])

    assert code == 0
    assert seen == {"dry_run": False, "propose": False}
