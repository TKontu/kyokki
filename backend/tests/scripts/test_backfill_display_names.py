"""Post-MVP frontier item 13: backfilling the existing catalog with a Finnish name.

`backfill_display_names.py` walks the catalog once and proposes a Finnish name for every
product with none yet, batched through the shared gateway helper; a cook's own name is never
touched. `--refresh-model` also re-proposes every name that came from an earlier model
proposal, so the operator can rerun once the prompt carries printed receipt aliases
(2026-10-03 production backfill finding).
"""

from uuid import uuid4

import pytest
from scripts import backfill_display_names
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import product_master as crud_product
from app.models.product_master import ProductMaster
from app.models.store_product_alias import StoreProductAlias


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


async def _product(
    db: AsyncSession, name: str, *, category: str = "dairy"
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category=category,
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _reload(db: AsyncSession, product: ProductMaster) -> ProductMaster:
    return await db.get(ProductMaster, product.id, populate_existing=True)  # type: ignore[return-value]


class TestCandidates:
    async def test_a_missing_name_is_a_candidate(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")

        found = await backfill_display_names.candidates(db_session)

        assert product.id in {p.id for p in found}

    async def test_a_cook_name_is_never_a_candidate(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Oma maito", source="cook"
        )
        await db_session.commit()

        found = await backfill_display_names.candidates(db_session)

        assert product.id not in {p.id for p in found}

    async def test_a_model_name_is_not_a_candidate_by_default(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Maito", source="model"
        )
        await db_session.commit()

        found = await backfill_display_names.candidates(db_session)

        assert product.id not in {p.id for p in found}

    async def test_refresh_model_adds_back_every_model_name(
        self, db_session: AsyncSession, categories
    ) -> None:
        model_named = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, model_named, language="fi", name="Maito", source="model"
        )
        cook_named = await _product(db_session, "Oats", category="pantry")
        await crud_product.set_display_name(
            db_session, cook_named, language="fi", name="Omat kaurat", source="cook"
        )
        missing = await _product(db_session, "Carrot", category="produce")
        await db_session.commit()

        found = await backfill_display_names.candidates(db_session, refresh_model=True)

        ids = {p.id for p in found}
        assert model_named.id in ids
        assert missing.id in ids
        assert cook_named.id not in ids


class TestProposeInBatches:
    async def test_it_batches_one_request_at_a_time(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        products = [
            await _product(db_session, f"Product {n}", category="snacks")
            for n in range(45)
        ]
        calls: list[list[str]] = []

        async def fake_propose(names, **kwargs):
            calls.append(list(names))
            return [f"Nimi {n}" for n in range(len(names))]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        changes = await backfill_display_names.propose_in_batches(
            products, batch_size=20, sessions=session_factory
        )

        assert [len(c) for c in calls] == [20, 20, 5]
        assert len(changes) == 45

    async def test_each_finished_batch_is_handed_to_on_batch(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        products = [
            await _product(db_session, f"Product {n}", category="snacks")
            for n in range(3)
        ]

        async def fake_propose(names, **kwargs):
            return [f"Nimi {n}" for n in range(len(names))]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )
        seen_batches: list[int] = []

        async def on_batch(batch_changes):
            seen_batches.append(len(batch_changes))

        await backfill_display_names.propose_in_batches(
            products, batch_size=2, on_batch=on_batch, sessions=session_factory
        )

        assert seen_batches == [2, 1]

    async def test_a_batch_the_model_could_not_answer_is_skipped(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return None

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        changes = await backfill_display_names.propose_in_batches(
            [product], batch_size=20, sessions=session_factory
        )

        assert changes == []

    async def test_the_batch_carries_each_products_printed_aliases(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = await _product(db_session, "Smoked tofu")
        db_session.add(
            StoreProductAlias(
                product_master_id=product.id,
                store_chain="s-market",
                receipt_name="TOFU KYLMÄSAVU LUOMU",
            )
        )
        await db_session.commit()
        seen: dict = {}

        async def fake_propose(names, *, aliases=None, **kwargs):
            seen["aliases"] = aliases
            return ["Kylmäsavutofu"]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        await backfill_display_names.propose_in_batches(
            [product], batch_size=20, sessions=session_factory
        )

        assert seen["aliases"] == [["TOFU KYLMÄSAVU LUOMU"]]


class TestApplyChanges:
    async def test_it_writes_every_planned_change(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        changes = [
            backfill_display_names.Change(product.id, "Milk", "Maito"),
        ]

        applied = await backfill_display_names.apply_changes(db_session, changes)

        assert applied == 1
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Maito"}
        assert stored.display_name_sources == {"fi": "model"}

    async def test_a_cook_choice_made_meanwhile_is_not_overwritten(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        changes = [backfill_display_names.Change(product.id, "Milk", "Maito")]
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Oma maito", source="cook"
        )
        await db_session.commit()

        applied = await backfill_display_names.apply_changes(db_session, changes)

        assert applied == 0
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Oma maito"}

    async def test_a_refreshed_model_name_does_overwrite_the_old_one(
        self, db_session: AsyncSession, categories
    ) -> None:
        """`--refresh-model`'s whole point: the planned change must win over the model
        name that was already there when it was planned."""
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Maito", source="model"
        )
        await db_session.commit()
        changes = [
            backfill_display_names.Change(product.id, "Milk", "Kermamaito"),
        ]

        applied = await backfill_display_names.apply_changes(db_session, changes)

        assert applied == 1
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Kermamaito"}


class TestBackfillWording:
    async def test_dry_run_says_would_get(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return ["Maito"]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        await backfill_display_names.backfill(dry_run=True, sessions=session_factory)

        out = capsys.readouterr().out
        assert "would get a Finnish name" in out
        assert "will get a Finnish name" not in out

    async def test_a_real_run_says_will_get(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return ["Maito"]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        await backfill_display_names.backfill(dry_run=False, sessions=session_factory)

        out = capsys.readouterr().out
        assert "will get a Finnish name" in out
        assert "would get a Finnish name" not in out

    async def test_dry_run_writes_nothing(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return ["Maito"]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        await backfill_display_names.backfill(dry_run=True, sessions=session_factory)

        stored = await _reload(db_session, product)
        assert stored.display_names == {}


class TestRefreshModelEndToEnd:
    async def test_refresh_model_re_proposes_a_model_name(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = await _product(db_session, "Coffee oat milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Kauramaito", source="model"
        )
        await db_session.commit()

        async def fake_propose(names, **kwargs):
            assert names == ["Coffee oat milk"]
            return ["Kahvillinen kauramaito"]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        await backfill_display_names.backfill(
            dry_run=False, refresh_model=True, sessions=session_factory
        )

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Kahvillinen kauramaito"}

    async def test_without_refresh_model_a_model_name_is_left_alone(
        self,
        db_session: AsyncSession,
        categories,
        session_factory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        product = await _product(db_session, "Coffee oat milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Kauramaito", source="model"
        )
        await db_session.commit()
        called = False

        async def fake_propose(names, **kwargs):
            nonlocal called
            called = True
            return ["Nope"]

        monkeypatch.setattr(
            backfill_display_names, "propose_finnish_names", fake_propose
        )

        await backfill_display_names.backfill(dry_run=False, sessions=session_factory)

        assert called is False
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Kauramaito"}


def test_main_parses_dry_run_batch_size_and_refresh_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    async def fake_backfill(
        *,
        dry_run,
        batch_size,
        refresh_model,
        sessions=backfill_display_names._default_sessions,
    ):
        seen["dry_run"] = dry_run
        seen["batch_size"] = batch_size
        seen["refresh_model"] = refresh_model
        return []

    monkeypatch.setattr(backfill_display_names, "backfill", fake_backfill)

    code = backfill_display_names.main(
        ["--dry-run", "--batch-size", "5", "--refresh-model"]
    )

    assert code == 0
    assert seen == {"dry_run": True, "batch_size": 5, "refresh_model": True}


def test_main_defaults_to_a_real_non_refreshing_run_batched_by_20(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = {}

    async def fake_backfill(
        *,
        dry_run,
        batch_size,
        refresh_model,
        sessions=backfill_display_names._default_sessions,
    ):
        seen["dry_run"] = dry_run
        seen["batch_size"] = batch_size
        seen["refresh_model"] = refresh_model
        return []

    monkeypatch.setattr(backfill_display_names, "backfill", fake_backfill)

    code = backfill_display_names.main([])

    assert code == 0
    assert seen == {"dry_run": False, "batch_size": 20, "refresh_model": False}
