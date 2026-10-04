"""Post-MVP frontier item 13: a product's name in the cook's chosen display language.

Operator ruling (2026-10-02): a selectable display language, with receipts kept as printed.
A new product gets a Finnish name proposed by the model in the background, the same shape as
the exact-emoji proposal (`tests/services/test_product_emoji.py` is this file's template): a
batch of one request, through the shared gateway helper, never overwriting a cook's own name.
"""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import product_master as crud_product
from app.models.product_master import ProductMaster
from app.services import display_names

# Captured before any test runs, so it survives the autouse `_no_model_selection` fixture
# (tests/conftest.py) patching `display_names._post_proposal` for every other test.
REAL_POST_PROPOSAL = display_names._post_proposal


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, request) -> None:
    """The job opens its own session; in a DB test it is the test's, so its rows are visible."""
    if "db_session" in request.fixturenames:
        monkeypatch.setattr(
            display_names, "open_session", request.getfixturevalue("session_factory")
        )


@pytest.fixture
def broadcast():
    with patch(
        "app.services.display_names.broadcast_product_update", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


async def _product(
    db: AsyncSession, name: str = "Milk", *, category: str = "dairy"
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


class TestSetDisplayName:
    """`crud.set_display_name` (F2 review): clearing, and the length limit."""

    async def test_an_empty_name_clears_an_existing_row(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Maito", source="cook"
        )
        await db_session.commit()

        await crud_product.set_display_name(
            db_session, product, language="fi", name="", source="cook"
        )
        await db_session.commit()

        stored = await _reload(db_session, product)
        assert stored.display_names == {}

    async def test_a_whitespace_name_clears_too(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Maito", source="cook"
        )
        await db_session.commit()

        await crud_product.set_display_name(
            db_session, product, language="fi", name="   ", source="cook"
        )
        await db_session.commit()

        stored = await _reload(db_session, product)
        assert stored.display_names == {}

    async def test_clearing_a_language_with_no_row_does_nothing(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")

        await crud_product.set_display_name(
            db_session, product, language="fi", name="", source="cook"
        )
        await db_session.commit()

        stored = await _reload(db_session, product)
        assert stored.display_names == {}

    async def test_a_name_over_100_characters_raises(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")

        with pytest.raises(crud_product.DisplayNameTooLong):
            await crud_product.set_display_name(
                db_session, product, language="fi", name="M" * 101, source="cook"
            )

    async def test_a_name_of_exactly_100_characters_is_fine(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        name = "M" * 100

        await crud_product.set_display_name(
            db_session, product, language="fi", name=name, source="cook"
        )
        await db_session.commit()

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": name}


class TestSupportedLanguages:
    def test_finnish_is_supported_english_is_not_a_code(self) -> None:
        assert display_names.is_supported("fi") is True
        assert "en" not in display_names.SUPPORTED_LANGUAGES


class TestParseProposals:
    def test_a_usable_answer_is_kept(self) -> None:
        content = json.dumps({"r": [{"i": 1, "fi": "Maito"}]})

        assert display_names._parse_proposals(content, ["Milk"]) == ["Maito"]

    def test_a_blank_name_becomes_none(self) -> None:
        content = json.dumps({"r": [{"i": 1, "fi": "   "}]})

        assert display_names._parse_proposals(content, ["Milk"]) == [None]

    def test_bad_numbering_makes_the_whole_batch_unusable(self) -> None:
        content = json.dumps({"r": [{"i": 1, "fi": "Maito"}]})

        assert display_names._parse_proposals(content, ["A", "B"]) is None

    def test_no_json_is_unusable(self) -> None:
        assert display_names._parse_proposals("not json", ["A"]) is None

    def test_rows_are_matched_by_number_not_by_order(self) -> None:
        content = json.dumps(
            {"r": [{"i": 2, "fi": "Porkkana"}, {"i": 1, "fi": "Tomaatti"}]}
        )

        assert display_names._parse_proposals(content, ["Tomato", "Carrot"]) == [
            "Tomaatti",
            "Porkkana",
        ]


def _gateway(monkeypatch: pytest.MonkeyPatch, respond) -> dict:
    """Route `_post_proposal`'s client to a fake gateway; returns what it saw."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.setdefault("requests", []).append(request)
        seen["headers"] = dict(request.headers)
        return respond(request, len(seen["requests"]))

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client(**kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real(transport=transport)

    monkeypatch.setattr(display_names.httpx, "AsyncClient", client)
    return seen


def _reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class TestGatewayRules:
    """The retry, drain-backoff and timeout-budget rules live in the shared
    `services/llm_http.py` (GW-1) and are tested there; these tests only prove
    `_post_proposal` wires into it correctly, mirroring `test_product_emoji.py`'s own."""

    async def test_it_sends_a_bearer_key_and_a_timeout_of_at_least_300s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _gateway(monkeypatch, lambda request, n: _reply('{"r": []}'))
        monkeypatch.setattr(settings, "LLM_API_KEY", "the-key")
        monkeypatch.setattr(settings, "LLM_TIMEOUT", 10.0)

        await REAL_POST_PROPOSAL({"model": "m"})

        assert seen["headers"]["authorization"] == "Bearer the-key"
        assert seen["timeout"] > 299.0

    async def test_a_timeout_is_never_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("too slow", request=request)

        real = httpx.AsyncClient
        monkeypatch.setattr(
            display_names.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

        with pytest.raises(display_names.DisplayNameProposalError, match="ReadTimeout"):
            await REAL_POST_PROPOSAL({"model": "m"})

        assert calls == 1

    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_401_or_403_is_logged_without_the_key_and_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        status: int,
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "super-secret-key")
        _gateway(monkeypatch, lambda request, n: httpx.Response(status))

        with pytest.raises(display_names.DisplayNameProposalError, match="LLM_API_KEY"):
            await REAL_POST_PROPOSAL({"model": "m"})

        assert "super-secret-key" not in caplog.text
        assert "rejected LLM_API_KEY" in caplog.text


class TestProposeFinnishNames:
    async def test_a_model_failure_leaves_nothing_to_apply(self) -> None:
        async def failing(payload):
            raise display_names.DisplayNameProposalError("boom")

        result = await display_names.propose_finnish_names(["Milk"], complete=failing)

        assert result is None

    async def test_a_usable_answer_is_returned_in_order(self) -> None:
        async def complete(payload):
            return json.dumps(
                {"r": [{"i": 1, "fi": "Maito"}, {"i": 2, "fi": "Porkkana"}]}
            )

        result = await display_names.propose_finnish_names(
            ["Milk", "Carrot"], complete=complete
        )

        assert result == ["Maito", "Porkkana"]

    async def test_no_names_makes_no_request(self) -> None:
        called = False

        async def complete(payload):
            nonlocal called
            called = True
            return "{}"

        assert await display_names.propose_finnish_names([], complete=complete) == []
        assert called is False


# --- the on-create background hook ------------------------------------------------------------


class TestOnCreateHook:
    async def test_a_miss_asks_the_model_and_stores_the_name(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            assert names == ["Milk"]
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Maito"}
        assert stored.display_name_sources == {"fi": "model"}
        broadcast.assert_awaited_once()

    async def test_a_model_failure_leaves_the_product_without_a_name(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return None

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.display_names == {}
        broadcast.assert_not_awaited()

    async def test_a_cook_set_name_is_never_asked_about(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Oma maito", source="cook"
        )
        await db_session.commit()
        called = False

        async def fake_propose(names, **kwargs):
            nonlocal called
            called = True
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_create(product.id)

        assert called is False
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Oma maito"}

    async def test_a_cleared_name_can_be_filled_by_a_later_proposal(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        """F2 review: an empty cook row used to count as "already has a row", so this
        case silently never proposed again once cleared."""
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="  ", source="cook"
        )
        await db_session.commit()
        stored = await _reload(db_session, product)
        assert stored.display_names == {}

        async def fake_propose(names, **kwargs):
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Maito"}
        assert stored.display_name_sources == {"fi": "model"}

    async def test_a_cook_who_sets_it_while_the_model_is_asked_wins(
        self, db_session: AsyncSession, categories, broadcast, session_factory
    ) -> None:
        """The second, pre-write check: the cook may get there between the proposal
        going out and the answer coming back."""
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            async with session_factory() as db:
                raced = await db.get(ProductMaster, product.id)
                await crud_product.set_display_name(
                    db, raced, language="fi", name="Oma maito", source="cook"
                )
                await db.commit()
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Oma maito"}

    async def test_a_product_that_is_gone_is_skipped(
        self, db_session: AsyncSession, categories
    ) -> None:
        await display_names._propose_one_on_create(uuid4())  # does not raise


class TestBatchedProposals:
    """F3 review: one gateway call covers every new product in one `schedule_estimates`
    batch, the same shape `catalog_estimates.estimate_new_products` already uses for the
    shelf life - a receipt confirm that creates N products must not make N requests."""

    async def test_one_call_covers_the_whole_batch(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        tomato = await _product(db_session, "Tomato")
        carrot = await _product(db_session, "Carrot")
        calls = []

        FI = {"Tomato": "Tomaatti", "Carrot": "Porkkana"}

        async def fake_propose(names, **kwargs):
            calls.append(list(names))
            return [FI.get(n) for n in names]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products(
                [tomato.id, carrot.id]
            )

        assert calls == [["Tomato", "Carrot"]]
        stored_tomato = await _reload(db_session, tomato)
        stored_carrot = await _reload(db_session, carrot)
        assert stored_tomato.display_names == {"fi": "Tomaatti"}
        assert stored_carrot.display_names == {"fi": "Porkkana"}

    async def test_a_product_that_already_has_a_name_is_left_out_of_the_request(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        named = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, named, language="fi", name="Maito", source="cook"
        )
        await db_session.commit()
        unnamed = await _product(db_session, "Carrot")
        calls = []

        async def fake_propose(names, **kwargs):
            calls.append(list(names))
            return ["Porkkana"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products(
                [named.id, unnamed.id]
            )

        assert calls == [["Carrot"]]

    async def test_no_products_need_one_makes_no_request(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Maito", source="cook"
        )
        await db_session.commit()
        called = False

        async def fake_propose(names, **kwargs):
            nonlocal called
            called = True
            return []

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products([product.id])

        assert called is False

    async def test_one_unusable_row_does_not_drop_the_rest_of_the_batch(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        tomato = await _product(db_session, "Tomato")
        carrot = await _product(db_session, "Carrot")

        FI = {"Carrot": "Porkkana"}

        async def fake_propose(names, **kwargs):
            return [FI.get(n) for n in names]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products(
                [tomato.id, carrot.id]
            )

        stored_tomato = await _reload(db_session, tomato)
        stored_carrot = await _reload(db_session, carrot)
        assert stored_tomato.display_names == {}
        assert stored_carrot.display_names == {"fi": "Porkkana"}

    async def test_one_products_write_failure_does_not_drop_the_rest_of_the_batch(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        tomato = await _product(db_session, "Tomato")
        carrot = await _product(db_session, "Carrot")
        real_set = crud_product.set_display_name
        FI = {"Tomato": "Tomaatti", "Carrot": "Porkkana"}

        async def fake_propose(names, **kwargs):
            return [FI.get(n) for n in names]

        async def flaky_set(db, product, **kwargs):
            if str(product.canonical_name) == "Tomato":
                raise RuntimeError("boom")
            return await real_set(db, product, **kwargs)

        with (
            patch.object(display_names, "propose_finnish_names", new=fake_propose),
            patch.object(crud_product, "set_display_name", new=flaky_set),
        ):
            await display_names.propose_display_names_for_new_products(
                [tomato.id, carrot.id]
            )

        stored_tomato = await _reload(db_session, tomato)
        stored_carrot = await _reload(db_session, carrot)
        assert stored_tomato.display_names == {}
        assert stored_carrot.display_names == {"fi": "Porkkana"}

    async def test_a_malformed_answer_leaves_the_whole_batch_untouched(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        tomato = await _product(db_session, "Tomato")
        carrot = await _product(db_session, "Carrot")

        async def fake_propose(names, **kwargs):
            return None

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products(
                [tomato.id, carrot.id]
            )

        stored_tomato = await _reload(db_session, tomato)
        stored_carrot = await _reload(db_session, carrot)
        assert stored_tomato.display_names == {}
        assert stored_carrot.display_names == {}
        broadcast.assert_not_awaited()

    async def test_propose_for_new_products_never_raises_reading_the_batch(
        self, db_session: AsyncSession, categories
    ) -> None:
        async def boom(product_ids):
            raise RuntimeError("nope")

        with patch.object(display_names, "_pending_products", new=boom):
            await display_names.propose_display_names_for_new_products([uuid4()])

    async def test_propose_for_new_products_never_raises_storing_one(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return ["Maito"]

        async def boom(*args, **kwargs):
            raise RuntimeError("nope")

        with (
            patch.object(display_names, "propose_finnish_names", new=fake_propose),
            patch.object(crud_product, "set_display_name", new=boom),
        ):
            await display_names.propose_display_names_for_new_products([product.id])

        stored = await _reload(db_session, product)
        assert stored.display_names == {}

    def test_schedule_display_names_queues_a_background_task(self) -> None:
        from fastapi import BackgroundTasks

        tasks = BackgroundTasks()
        display_names.schedule_display_names(tasks, [uuid4()])

        assert len(tasks.tasks) == 1

    def test_schedule_display_names_does_nothing_for_no_products(self) -> None:
        from fastapi import BackgroundTasks

        tasks = BackgroundTasks()
        display_names.schedule_display_names(tasks, [])

        assert len(tasks.tasks) == 0


class TestNoAccidentalGatewayCalls:
    """The autouse `_no_model_selection` fixture (tests/conftest.py) must patch this
    module's own model call too - otherwise every test that creates a product sends a
    real request to `settings.LLM_BASE_URL` (the same lesson PR #137 review drew for
    `product_emoji`)."""

    async def test_the_autouse_fixture_keeps_this_module_off_the_real_gateway(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args, **kwargs):
            raise AssertionError("display_names tried to open a real httpx connection")

        monkeypatch.setattr(httpx.AsyncClient, "__init__", _boom)

        result = await display_names.propose_finnish_names(["Milk"])

        assert result is None

    def test_the_fixture_really_does_replace_the_function(self) -> None:
        assert display_names._post_proposal is not REAL_POST_PROPOSAL


class TestBuildPromptAliases:
    """Task 2: the prompt carries up to three printed receipt aliases per product, and
    with none at all it behaves exactly as it did before this lane."""

    def test_no_aliases_matches_todays_prompt(self) -> None:
        with_none = display_names._build_prompt(["Milk"])
        with_empty_lists = display_names._build_prompt(["Milk"], [[]])

        assert with_none == with_empty_lists
        assert "receipt" not in with_none.lower()
        assert with_none == (
            "You translate grocery product names for a Finnish home cook's kitchen\n"
            "inventory app. For each generic English product name below, give the "
            "natural Finnish word or\nshort phrase a Finnish cook would use for it on "
            "a shopping list or in the fridge - not a\nliteral dictionary translation, "
            "and not a brand name. Keep it short, in Finnish sentence case.\n\n"
            "Products, numbered:\n1. Milk\n\n"
            'Answer with JSON only: {"r": [{"i": <number>, "fi": "<name>"}, ...]}, '
            "one row per product,\nin the same order they were given."
        )

    def test_aliases_appear_in_the_prompt(self) -> None:
        prompt = display_names._build_prompt(
            ["Smoked tofu"], [["TOFU KYLMÄSAVU LUOMU", "KYLMÄSAVUTOFU 200G"]]
        )

        assert "TOFU KYLMÄSAVU LUOMU" in prompt
        assert "KYLMÄSAVUTOFU 200G" in prompt
        assert "receipt" in prompt.lower()
        assert "LUOMU" in prompt  # the worked example, not just the alias text

    def test_a_product_with_no_alias_in_a_mixed_batch_still_gets_a_plain_line(
        self,
    ) -> None:
        prompt = display_names._build_prompt(
            ["Milk", "Smoked tofu"], [[], ["TOFU KYLMÄSAVU LUOMU"]]
        )

        assert "1. Milk\n" in prompt
        assert "2. Smoked tofu (printed on receipts: TOFU KYLMÄSAVU LUOMU)" in prompt


class TestPrintedAliases:
    """`printed_aliases`: up to three distinct printed names, newest first."""

    async def test_no_aliases_is_an_empty_list(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Milk")

        assert await display_names.printed_aliases(db_session, product.id) == []

    async def test_newest_first_deduplicated_and_capped_at_three(
        self, db_session: AsyncSession, categories
    ) -> None:
        from datetime import UTC, datetime, timedelta

        from app.models.store_product_alias import StoreProductAlias

        product = await _product(db_session, "Smoked tofu")
        now = datetime.now(UTC)
        rows = [
            StoreProductAlias(
                product_master_id=product.id,
                store_chain=chain,
                receipt_name=name,
                last_seen=now - timedelta(days=days),
            )
            for chain, name, days in [
                ("s-market", "TOFU KYLMÄSAVU LUOMU", 10),
                ("prisma", "TOFU KYLMÄSAVU LUOMU", 5),  # same text, newer
                ("lidl", "KYLMÄSAVUTOFU 200G", 1),
                ("k-citymarket", "KS TOFU", 20),
            ]
        ]
        for row in rows:
            db_session.add(row)
        await db_session.commit()

        aliases = await display_names.printed_aliases(db_session, product.id)

        assert aliases == ["KYLMÄSAVUTOFU 200G", "TOFU KYLMÄSAVU LUOMU", "KS TOFU"]


class TestBatchCarriesAliases:
    """Task 2: the on-create batch passes each product's own printed aliases through."""

    async def test_the_batch_passes_each_products_aliases(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        from app.models.store_product_alias import StoreProductAlias

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
            seen["names"] = list(names)
            seen["aliases"] = aliases
            return ["Kylmäsavutofu"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products([product.id])

        assert seen["names"] == ["Smoked tofu"]
        assert seen["aliases"] == [["TOFU KYLMÄSAVU LUOMU"]]

    async def test_a_product_with_no_alias_sends_an_empty_list(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Milk")
        seen: dict = {}

        async def fake_propose(names, *, aliases=None, **kwargs):
            seen["aliases"] = aliases
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names.propose_display_names_for_new_products([product.id])

        assert seen["aliases"] == [[]]


class TestRenameReproposal:
    """Task 1: a rename re-proposes the Finnish name for a model (or missing) name,
    and never for the cook's own."""

    async def test_a_model_name_is_reproposed_after_a_rename(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Coffee oat milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Kauramaito", source="model"
        )
        await db_session.commit()
        product.canonical_name = "Oat milk"
        await db_session.commit()
        seen: dict = {}

        async def fake_propose(names, **kwargs):
            seen["names"] = list(names)
            return ["Kahvillinen kauramaito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_rename(product.id)

        assert seen["names"] == ["Oat milk"]
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Kahvillinen kauramaito"}
        assert stored.display_name_sources == {"fi": "model"}
        broadcast.assert_awaited_once()

    async def test_a_missing_name_is_proposed_after_a_rename_too(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Milk")

        async def fake_propose(names, **kwargs):
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_rename(product.id)

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Maito"}
        assert stored.display_name_sources == {"fi": "model"}

    async def test_a_cook_name_is_never_reproposed(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Oma maito", source="cook"
        )
        await db_session.commit()
        called = False

        async def fake_propose(names, **kwargs):
            nonlocal called
            called = True
            return ["Maito"]

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_rename(product.id)

        assert called is False
        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Oma maito"}

    async def test_the_stale_model_name_stays_until_the_new_one_lands(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        """No flash of English: a model failure must leave the old name in place."""
        product = await _product(db_session, "Coffee oat milk")
        await crud_product.set_display_name(
            db_session, product, language="fi", name="Kauramaito", source="model"
        )
        await db_session.commit()

        async def failing_propose(names, **kwargs):
            return None

        with patch.object(display_names, "propose_finnish_names", new=failing_propose):
            await display_names._propose_one_on_rename(product.id)

        stored = await _reload(db_session, product)
        assert stored.display_names == {"fi": "Kauramaito"}

    async def test_a_gone_product_is_skipped(
        self, db_session: AsyncSession, categories
    ) -> None:
        await display_names._propose_one_on_rename(uuid4())  # does not raise

    async def test_the_renames_prompt_carries_printed_aliases(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        from app.models.store_product_alias import StoreProductAlias

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

        with patch.object(display_names, "propose_finnish_names", new=fake_propose):
            await display_names._propose_one_on_rename(product.id)

        assert seen["aliases"] == [["TOFU KYLMÄSAVU LUOMU"]]

    def test_schedule_queues_a_background_task(self) -> None:
        from fastapi import BackgroundTasks

        tasks = BackgroundTasks()
        display_names.schedule_display_name_rename(tasks, uuid4())

        assert len(tasks.tasks) == 1
