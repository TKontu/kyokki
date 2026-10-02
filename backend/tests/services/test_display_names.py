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

    async def test_propose_for_new_products_never_raises(
        self, db_session: AsyncSession, categories
    ) -> None:
        async def boom(product_id: object) -> None:
            raise RuntimeError("nope")

        with patch.object(display_names, "_propose_one_on_create", new=boom):
            await display_names.propose_display_names_for_new_products([uuid4()])

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
