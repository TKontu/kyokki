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

        changes, misses = await backfill_emoji.plan(db_session)

        (change,) = [c for c in changes if c.id == product.id]
        assert change.emoji == "🧀"
        assert change.match == EmojiMatch.EXACT
        assert misses == []

    async def test_a_gap_product_is_planned_as_none(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Mozzarella")

        changes, _ = await backfill_emoji.plan(db_session)

        (change,) = [c for c in changes if c.id == product.id]
        assert change.emoji is None
        assert change.match == EmojiMatch.NONE

    async def test_a_settled_product_is_not_replanned(
        self, db_session: AsyncSession, categories
    ) -> None:
        await _product(db_session, "Gouda", emoji="🧀", emoji_match=EmojiMatch.EXACT)

        changes, misses = await backfill_emoji.plan(db_session)

        assert changes == []
        assert misses == []

    async def test_non_food_is_skipped(
        self, db_session: AsyncSession, categories
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        product = await _product(db_session, "Toilet paper", category="pantry")

        changes, misses = await backfill_emoji.plan(db_session)

        assert product.id not in {c.id for c in changes}
        assert product.id not in {p.id for p in misses}

    async def test_cook_is_never_touched(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(
            db_session, "Gouda", emoji="🥨", emoji_match=EmojiMatch.COOK
        )

        changes, misses = await backfill_emoji.plan(db_session)

        assert product.id not in {c.id for c in changes}
        assert product.id not in {p.id for p in misses}

    async def test_cleared_is_never_touched(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda", emoji_match=EmojiMatch.CLEARED)

        changes, misses = await backfill_emoji.plan(db_session)

        assert product.id not in {c.id for c in changes}
        assert product.id not in {p.id for p in misses}

    async def test_an_unknown_name_is_a_miss_not_a_change(
        self, db_session: AsyncSession, categories
    ) -> None:
        """`plan()` never calls the model - it only collects misses for the caller to
        propose, in batches, if it asks to."""
        product = await _product(
            db_session, "A Brand New Kind Of Snack", category="snacks"
        )

        changes, misses = await backfill_emoji.plan(db_session)

        assert product.id not in {c.id for c in changes}
        assert [p.id for p in misses] == [product.id]


class TestProposeInBatches:
    async def test_it_batches_one_request_at_a_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.product_emoji import ProposalAnswer

        misses = [
            ProductMaster(
                id=uuid4(),
                canonical_name=f"Miss {n}",
                category="snacks",
                storage_type="pantry",
                default_shelf_life_days=90,
                unit_type="count",
                default_unit="pcs",
            )
            for n in range(45)
        ]
        calls: list[list[str]] = []

        async def fake_propose(names, **kwargs):
            calls.append(list(names))
            return [ProposalAnswer("🥨", EmojiMatch.PROPOSED) for _ in names]

        monkeypatch.setattr(backfill_emoji.product_emoji, "propose", fake_propose)

        changes = await backfill_emoji.propose_in_batches(misses, batch_size=20)

        assert [len(c) for c in calls] == [20, 20, 5]
        assert len(changes) == 45
        assert all(c.match == EmojiMatch.PROPOSED and c.emoji == "🥨" for c in changes)

    async def test_each_finished_batch_is_handed_to_on_batch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.product_emoji import ProposalAnswer

        misses = [
            ProductMaster(
                id=uuid4(),
                canonical_name=f"Miss {n}",
                category="snacks",
                storage_type="pantry",
                default_shelf_life_days=90,
                unit_type="count",
                default_unit="pcs",
            )
            for n in range(3)
        ]

        async def fake_propose(names, **kwargs):
            return [ProposalAnswer(None, EmojiMatch.NONE) for _ in names]

        monkeypatch.setattr(backfill_emoji.product_emoji, "propose", fake_propose)
        seen_batches: list[int] = []

        async def on_batch(batch_changes):
            seen_batches.append(len(batch_changes))

        await backfill_emoji.propose_in_batches(misses, batch_size=2, on_batch=on_batch)

        assert seen_batches == [2, 1]

    async def test_a_batch_the_model_could_not_answer_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        miss = ProductMaster(
            id=uuid4(),
            canonical_name="Miss",
            category="snacks",
            storage_type="pantry",
            default_shelf_life_days=90,
            unit_type="count",
            default_unit="pcs",
        )

        async def fake_propose(names, **kwargs):
            return None

        monkeypatch.setattr(backfill_emoji.product_emoji, "propose", fake_propose)

        changes = await backfill_emoji.propose_in_batches([miss], batch_size=20)

        assert changes == []


class TestApplyChanges:
    async def test_it_writes_every_planned_change(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        changes, _ = await backfill_emoji.plan(db_session)

        applied = await backfill_emoji.apply_changes(db_session, changes)

        assert applied == len(changes)
        stored = await _reload(db_session, product)
        assert stored.emoji == "🧀"
        assert stored.emoji_match == EmojiMatch.EXACT

    async def test_a_cook_choice_made_meanwhile_is_not_overwritten(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        changes, _ = await backfill_emoji.plan(db_session)
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

    async def test_propose_applies_each_batch_as_it_answers(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A run interrupted after the first batch must keep it, so each batch is applied
        (not just reported) as soon as it comes back - not only at the very end."""
        from app.services.product_emoji import ProposalAnswer

        misses = [
            await _product(db_session, f"Miss {n}", category="snacks") for n in range(3)
        ]
        calls: list[int] = []

        async def fake_propose(names, **kwargs):
            calls.append(len(names))
            return [ProposalAnswer("🥨", EmojiMatch.PROPOSED) for _ in names]

        monkeypatch.setattr(backfill_emoji.product_emoji, "propose", fake_propose)

        await backfill_emoji.backfill(
            dry_run=False, propose=True, batch_size=2, sessions=session_factory
        )

        assert calls == [2, 1]
        for product in misses:
            stored = await _reload(db_session, product)
            assert stored.emoji == "🥨"
            assert stored.emoji_match == EmojiMatch.PROPOSED
        assert "applied" in capsys.readouterr().out


def test_main_parses_dry_run_propose_and_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    async def fake_backfill(
        *, dry_run, propose, batch_size, sessions=backfill_emoji._default_sessions
    ):
        seen["dry_run"] = dry_run
        seen["propose"] = propose
        seen["batch_size"] = batch_size
        return []

    monkeypatch.setattr(backfill_emoji, "backfill", fake_backfill)

    code = backfill_emoji.main(["--dry-run", "--propose", "--batch-size", "5"])

    assert code == 0
    assert seen == {"dry_run": True, "propose": True, "batch_size": 5}


def test_main_defaults_to_a_real_non_proposing_run_batched_by_20(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    async def fake_backfill(
        *, dry_run, propose, batch_size, sessions=backfill_emoji._default_sessions
    ):
        seen["dry_run"] = dry_run
        seen["propose"] = propose
        seen["batch_size"] = batch_size
        return []

    monkeypatch.setattr(backfill_emoji, "backfill", fake_backfill)

    code = backfill_emoji.main([])

    assert code == 0
    assert seen == {"dry_run": False, "propose": False, "batch_size": 20}
