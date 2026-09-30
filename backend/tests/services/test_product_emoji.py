"""Q18 build: a product shows its exact Apple emoji, or none.

The operator's rule (2026-09-27, docs/spikes/Q18_exact_emoji.md): a tile shows an emoji only
when it is exact - the closest match is never shown - and non-food gets nothing at all. The
curated table decides most products with no model call; the model only proposes for a name the
table does not know, and a proposal is never shown before a person confirms it.
"""

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import product_master as crud_product
from app.models.non_food_name import NonFoodName
from app.models.product_emoji_learned import ProductEmojiLearned
from app.models.product_master import EmojiMatch, ProductMaster
from app.services import product_emoji
from app.services.non_food import remember_non_food
from app.services.product_emoji import (
    ProposalAnswer,
    UnknownEmoji,
    curated_lookup,
    load_reference,
    reference_emoji,
)


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, request) -> None:
    """The job opens its own session; in a DB test it is the test's, so its rows are visible."""
    if "db_session" in request.fixturenames:
        monkeypatch.setattr(
            product_emoji, "open_session", request.getfixturevalue("session_factory")
        )


@pytest.fixture
def broadcast():
    with patch(
        "app.services.product_emoji.broadcast_product_update", new_callable=AsyncMock
    ) as mock:
        yield mock


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


async def _product(
    db: AsyncSession, name: str = "Gouda", *, category: str = "cheese"
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


# --- the reference list and the curated table ----------------------------------------------


class TestReferenceList:
    def test_it_is_not_empty_and_has_no_household_emoji(self) -> None:
        reference = load_reference()

        assert reference
        names = {e["name"] for e in reference}
        assert "broccoli" in names
        assert "soap" not in names
        assert "roll of paper" not in names

    def test_every_reference_entry_has_an_emoji_and_a_name(self) -> None:
        for entry in load_reference():
            assert entry["e"]
            assert entry["name"]


class TestCuratedTable:
    def test_a_ruled_exact_name_returns_its_emoji(self) -> None:
        assert curated_lookup("Gouda") == ("🧀", EmojiMatch.EXACT)

    def test_it_is_case_and_space_insensitive(self) -> None:
        assert curated_lookup("  gouda   ") == ("🧀", EmojiMatch.EXACT)
        assert curated_lookup("GOUDA") == ("🧀", EmojiMatch.EXACT)

    def test_a_gap_list_name_returns_no_emoji_but_is_known(self) -> None:
        assert curated_lookup("Mozzarella") == (None, EmojiMatch.NONE)

    def test_family_does_not_imply_a_sibling_product(self) -> None:
        """Gouda -> exact does not make every cheese exact (the operator's own example)."""
        assert curated_lookup("Gouda") == ("🧀", EmojiMatch.EXACT)
        assert curated_lookup("Mozzarella") == (None, EmojiMatch.NONE)
        assert curated_lookup("Cottage cheese") == (None, EmojiMatch.NONE)

    def test_an_unknown_name_is_not_in_the_table_at_all(self) -> None:
        assert curated_lookup("Some Brand New Snack Nobody Has Heard Of") is None

    def test_it_has_109_exact_and_58_gap_products(self) -> None:
        from app.services.product_emoji import CURATED_FILE

        data = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
        exact = [p for p in data["products"] if p["emoji"]]
        gap = [p for p in data["products"] if not p["emoji"]]
        assert len(exact) == 109
        assert len(gap) == 58

    def test_every_curated_emoji_is_in_the_reference_list(self) -> None:
        from app.services.product_emoji import CURATED_FILE

        data = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
        known = reference_emoji()
        for product in data["products"]:
            if product["emoji"]:
                assert product["emoji"] in known, product

    def test_a_gap_row_may_carry_the_operators_icon_brief(self) -> None:
        assert product_emoji.gap_hint("Canned tomatoes")
        assert product_emoji.gap_hint("Tomato puree")
        assert product_emoji.gap_hint("Quark") is None  # no brief was given


class TestLookup:
    async def test_the_curated_table_wins_without_touching_the_learned_table(
        self, db_session: AsyncSession
    ) -> None:
        assert await product_emoji.lookup(db_session, "Gouda") == (
            "🧀",
            EmojiMatch.EXACT,
        )

    async def test_a_learned_name_resolves_once_confirmed(
        self, db_session: AsyncSession
    ) -> None:
        assert await product_emoji.lookup(db_session, "Brand New Thing") is None

        db_session.add(ProductEmojiLearned(generic_name="brand new thing", emoji="🥦"))
        await db_session.commit()

        assert await product_emoji.lookup(db_session, "Brand New Thing") == (
            "🥦",
            EmojiMatch.EXACT,
        )

    async def test_an_unknown_name_is_none(self, db_session: AsyncSession) -> None:
        assert (
            await product_emoji.lookup(db_session, "Nothing Like This Exists") is None
        )


class TestIsNonFood:
    async def test_a_remembered_non_food_name_is_recognised(
        self, db_session: AsyncSession
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        await db_session.commit()

        assert await product_emoji.is_non_food(db_session, "Toilet paper") is True

    async def test_a_food_name_is_not_non_food(self, db_session: AsyncSession) -> None:
        assert await product_emoji.is_non_food(db_session, "Gouda") is False

    async def test_it_is_seeded_directly_too(self, db_session: AsyncSession) -> None:
        db_session.add(NonFoodName(store_chain="K-Market", receipt_name="SOAP"))
        await db_session.commit()

        assert await product_emoji.is_non_food(db_session, "soap") is True


# --- applying a table hit on create ----------------------------------------------------------


class TestApplyOnCreate:
    async def test_a_curated_exact_name_is_applied_at_once(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda", category="cheese")

        applied = await product_emoji.apply_on_create(db_session, product)

        assert applied is True
        stored = await _reload(db_session, product)
        assert stored.emoji == "🧀"
        assert stored.emoji_match == EmojiMatch.EXACT

    async def test_a_gap_name_is_applied_as_none(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Mozzarella", category="cheese")

        applied = await product_emoji.apply_on_create(db_session, product)

        assert applied is True
        stored = await _reload(db_session, product)
        assert stored.emoji is None
        assert stored.emoji_match == EmojiMatch.NONE

    async def test_non_food_is_skipped_entirely(
        self, db_session: AsyncSession, categories
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        product = await _product(db_session, "Toilet paper", category="pantry")

        applied = await product_emoji.apply_on_create(db_session, product)

        assert applied is True
        stored = await _reload(db_session, product)
        assert stored.emoji is None
        assert stored.emoji_match is None

    async def test_an_unknown_name_is_a_miss(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(
            db_session, "A Brand New Kind Of Snack", category="snacks"
        )

        applied = await product_emoji.apply_on_create(db_session, product)

        assert applied is False
        stored = await _reload(db_session, product)
        assert stored.emoji is None
        assert stored.emoji_match is None


# --- confirm, reject, and the cook's own choice ----------------------------------------------


class TestConfirmAndReject:
    async def test_confirming_makes_it_exact_and_learns_the_name(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Brand New Thing", category="snacks")
        await crud_product.set_emoji(
            db_session, product, emoji="🥨", match=EmojiMatch.PROPOSED
        )

        confirmed = await product_emoji.confirm(db_session, product.id)

        assert confirmed is not None
        assert confirmed.emoji_match == EmojiMatch.EXACT
        assert confirmed.emoji == "🥨"
        learned = await crud_product.get_learned_emoji(db_session, "brand new thing")
        assert learned == "🥨"

    async def test_confirming_a_non_proposed_emoji_raises(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        await crud_product.set_emoji(
            db_session, product, emoji="🧀", match=EmojiMatch.EXACT
        )

        with pytest.raises(product_emoji.NotProposed):
            await product_emoji.confirm(db_session, product.id)

    async def test_confirming_an_unknown_product_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        assert await product_emoji.confirm(db_session, uuid4()) is None

    async def test_rejecting_makes_it_none_and_drops_the_emoji(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Brand New Thing", category="snacks")
        await crud_product.set_emoji(
            db_session, product, emoji="🥨", match=EmojiMatch.PROPOSED
        )

        rejected = await product_emoji.reject(db_session, product.id)

        assert rejected is not None
        assert rejected.emoji_match == EmojiMatch.NONE
        assert rejected.emoji is None
        # A rejected name is not learned - it may still be asked about again later.
        assert (
            await crud_product.get_learned_emoji(db_session, "brand new thing") is None
        )

    async def test_rejecting_a_non_proposed_emoji_raises(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")

        with pytest.raises(product_emoji.NotProposed):
            await product_emoji.reject(db_session, product.id)


class TestCookChoice:
    async def test_the_cook_can_pick_a_reference_emoji(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Mystery Item", category="snacks")

        chosen = await product_emoji.set_cook_choice(db_session, product.id, "🥨")

        assert chosen is not None
        assert chosen.emoji == "🥨"
        assert chosen.emoji_match == EmojiMatch.COOK

    async def test_the_cook_can_clear_it(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        await crud_product.set_emoji(
            db_session, product, emoji="🧀", match=EmojiMatch.EXACT
        )

        cleared = await product_emoji.set_cook_choice(db_session, product.id, None)

        assert cleared is not None
        assert cleared.emoji is None
        assert cleared.emoji_match == EmojiMatch.CLEARED

    async def test_an_emoji_outside_the_reference_list_is_refused(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Mystery Item", category="snacks")

        with pytest.raises(UnknownEmoji):
            await product_emoji.set_cook_choice(db_session, product.id, "🚀")

    async def test_cook_and_cleared_are_never_overwritten_by_a_table_hit(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session, "Gouda")
        await product_emoji.set_cook_choice(db_session, product.id, "🥨")

        # apply_on_create is only ever called for a brand-new product; a cook choice is
        # simply never revisited by it. Confirm that a fresh lookup does not clobber it if
        # somehow re-applied.
        applied_hit = await product_emoji.lookup(db_session, "Gouda")
        assert applied_hit == ("🧀", EmojiMatch.EXACT)
        stored = await _reload(db_session, product)
        assert stored.emoji == "🥨"
        assert stored.emoji_match == EmojiMatch.COOK


# --- the model proposal ----------------------------------------------------------------------


class TestParseProposals:
    def test_an_exact_answer_is_kept_as_proposed(self) -> None:
        reference = load_reference()
        content = json.dumps({"r": [{"i": 1, "e": "🥦", "m": "exact"}]})

        (answer,) = product_emoji._parse_proposals(content, ["Broccoli"], reference)

        assert answer == ProposalAnswer("🥦", EmojiMatch.PROPOSED)

    def test_borderline_and_none_both_become_none_with_no_emoji(self) -> None:
        reference = load_reference()
        content = json.dumps(
            {
                "r": [
                    {"i": 1, "e": "🧀", "m": "borderline"},
                    {"i": 2, "e": None, "m": "none"},
                ]
            }
        )

        answers = product_emoji._parse_proposals(
            content, ["Mozzarella", "Parsnip"], reference
        )

        assert answers == [
            ProposalAnswer(None, EmojiMatch.NONE),
            ProposalAnswer(None, EmojiMatch.NONE),
        ]

    def test_an_emoji_outside_the_reference_list_is_never_kept(self) -> None:
        reference = load_reference()
        content = json.dumps({"r": [{"i": 1, "e": "🚀", "m": "exact"}]})

        (answer,) = product_emoji._parse_proposals(content, ["Something"], reference)

        assert answer == ProposalAnswer(None, EmojiMatch.NONE)

    def test_bad_numbering_makes_the_whole_batch_unusable(self) -> None:
        reference = load_reference()
        content = json.dumps({"r": [{"i": 1, "e": "🥦", "m": "exact"}]})

        assert product_emoji._parse_proposals(content, ["A", "B"], reference) is None

    def test_no_json_is_unusable(self) -> None:
        assert (
            product_emoji._parse_proposals("not json", ["A"], load_reference()) is None
        )


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
        seen.setdefault("timeouts", []).append(kwargs.get("timeout"))
        return real(transport=transport)

    monkeypatch.setattr(product_emoji.httpx, "AsyncClient", client)
    return seen


def _reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class TestGatewayRules:
    """llama-swap requires a key since 2026-09-30 (the preamble); these rules are inline
    here rather than through the (possibly-unmerged) shared `services/llm_http.py`."""

    async def test_it_sends_a_bearer_key_and_a_timeout_of_at_least_300s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _gateway(monkeypatch, lambda request, n: _reply('{"r": []}'))
        monkeypatch.setattr(settings, "LLM_API_KEY", "the-key")
        monkeypatch.setattr(settings, "LLM_TIMEOUT", 10.0)

        await product_emoji._post_proposal({"model": "m"})

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
            product_emoji.httpx,
            "AsyncClient",
            lambda **kw: real(transport=httpx.MockTransport(handler)),
        )

        with pytest.raises(product_emoji.EmojiProposalError, match="timed out"):
            await product_emoji._post_proposal({"model": "m"})

        assert calls == 1

    async def test_a_503_with_retry_after_is_waited_out_and_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def respond(request: httpx.Request, n: int) -> httpx.Response:
            if n == 1:
                return httpx.Response(503, headers={"Retry-After": "3"})
            return _reply('{"r": []}')

        seen = _gateway(monkeypatch, respond)
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(product_emoji.asyncio, "sleep", fake_sleep)

        content = await product_emoji._post_proposal({"model": "m"})

        assert content == '{"r": []}'
        assert len(seen["requests"]) == 2
        assert sleeps == [3.0]

    async def test_the_retry_gets_the_remaining_budget_not_the_full_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A sibling review's finding: passing the constant timeout on every loop would let
        a chain of 503s run far longer than LLM_TIMEOUT (or its 300s floor) ever intended."""

        def respond(request: httpx.Request, n: int) -> httpx.Response:
            if n == 1:
                return httpx.Response(503, headers={"Retry-After": "1"})
            return _reply('{"r": []}')

        seen = _gateway(monkeypatch, respond)
        monkeypatch.setattr(product_emoji.asyncio, "sleep", AsyncMock())
        monkeypatch.setattr(settings, "LLM_TIMEOUT", 300.0)

        await product_emoji._post_proposal({"model": "m"})

        assert len(seen["timeouts"]) == 2
        assert seen["timeouts"][1] < seen["timeouts"][0]

    @pytest.mark.parametrize("bad", ["nan", "inf", "-5", "not-a-number"])
    async def test_an_unusable_retry_after_falls_back_to_the_default_wait(
        self, monkeypatch: pytest.MonkeyPatch, bad: str
    ) -> None:
        """`float()` parses "nan" and "inf" without raising, and `max(0.0, nan)` is `0.0` -
        none of these may be trusted as a wait time (a sibling review's finding)."""

        def respond(request: httpx.Request, n: int) -> httpx.Response:
            if n == 1:
                return httpx.Response(503, headers={"Retry-After": bad})
            return _reply('{"r": []}')

        _gateway(monkeypatch, respond)
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(product_emoji.asyncio, "sleep", fake_sleep)

        await product_emoji._post_proposal({"model": "m"})

        assert sleeps == [product_emoji.DEFAULT_RETRY_AFTER]

    async def test_a_retry_after_under_one_second_is_floored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def respond(request: httpx.Request, n: int) -> httpx.Response:
            if n == 1:
                return httpx.Response(503, headers={"Retry-After": "0.2"})
            return _reply('{"r": []}')

        _gateway(monkeypatch, respond)
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(product_emoji.asyncio, "sleep", fake_sleep)

        await product_emoji._post_proposal({"model": "m"})

        assert sleeps == [1.0]

    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_401_or_403_is_logged_without_the_key_and_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        status: int,
    ) -> None:
        monkeypatch.setattr(settings, "LLM_API_KEY", "super-secret-key")
        _gateway(monkeypatch, lambda request, n: httpx.Response(status))

        with pytest.raises(product_emoji.EmojiProposalError):
            await product_emoji._post_proposal({"model": "m"})

        assert "super-secret-key" not in caplog.text
        assert "rejected LLM_API_KEY" in caplog.text


class TestPropose:
    async def test_a_model_failure_leaves_nothing_to_apply(self) -> None:
        async def failing(payload):
            raise product_emoji.EmojiProposalError("boom")

        result = await product_emoji.propose(["Something"], complete=failing)

        assert result is None

    async def test_a_usable_answer_is_returned_in_order(self) -> None:
        async def complete(payload):
            return json.dumps(
                {
                    "r": [
                        {"i": 1, "e": "🥦", "m": "exact"},
                        {"i": 2, "e": None, "m": "none"},
                    ]
                }
            )

        result = await product_emoji.propose(["Broccoli", "Parsnip"], complete=complete)

        assert result == [
            ProposalAnswer("🥦", EmojiMatch.PROPOSED),
            ProposalAnswer(None, EmojiMatch.NONE),
        ]

    async def test_the_prompt_carries_the_operators_rulings_as_examples(self) -> None:
        seen = {}

        async def complete(payload):
            seen["prompt"] = payload["messages"][0]["content"]
            return json.dumps({"r": [{"i": 1, "e": None, "m": "none"}]})

        await product_emoji.propose(["Something"], complete=complete)

        prompt = seen["prompt"]
        assert "Gouda" in prompt and "Mozzarella" in prompt
        assert "ruled by the operator" in prompt

    async def test_no_names_makes_no_request(self) -> None:
        called = False

        async def complete(payload):
            nonlocal called
            called = True
            return "{}"

        assert await product_emoji.propose([], complete=complete) == []
        assert called is False


# --- the on-create background hook ------------------------------------------------------------


class TestOnCreateHook:
    async def test_a_table_hit_is_applied_and_announced(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Gouda")

        await product_emoji._apply_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.emoji == "🧀"
        assert stored.emoji_match == EmojiMatch.EXACT
        broadcast.assert_awaited_once()

    async def test_a_miss_asks_the_model_and_stores_a_proposal(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Brand New Thing", category="snacks")

        async def fake_propose(names, **kwargs):
            assert names == ["Brand New Thing"]
            return [ProposalAnswer("🥨", EmojiMatch.PROPOSED)]

        with patch.object(product_emoji, "propose", new=fake_propose):
            await product_emoji._apply_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.emoji == "🥨"
        assert stored.emoji_match == EmojiMatch.PROPOSED
        broadcast.assert_awaited_once()

    async def test_a_borderline_or_none_answer_leaves_the_product_unchanged(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Brand New Thing", category="snacks")

        async def fake_propose(names, **kwargs):
            return [ProposalAnswer(None, EmojiMatch.NONE)]

        with patch.object(product_emoji, "propose", new=fake_propose):
            await product_emoji._apply_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.emoji is None
        assert stored.emoji_match is None
        broadcast.assert_not_awaited()

    async def test_a_model_failure_leaves_the_product_unchanged_and_logs(
        self,
        db_session: AsyncSession,
        categories,
        broadcast,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        product = await _product(db_session, "Brand New Thing", category="snacks")

        async def fake_propose(names, **kwargs):
            return None

        with patch.object(product_emoji, "propose", new=fake_propose):
            await product_emoji._apply_one_on_create(product.id)

        stored = await _reload(db_session, product)
        assert stored.emoji is None
        assert stored.emoji_match is None
        broadcast.assert_not_awaited()

    async def test_non_food_is_skipped_with_no_model_call(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        product = await _product(db_session, "Toilet paper", category="pantry")
        called = False

        async def fake_propose(names, **kwargs):
            nonlocal called
            called = True
            return []

        with patch.object(product_emoji, "propose", new=fake_propose):
            await product_emoji._apply_one_on_create(product.id)

        assert called is False
        stored = await _reload(db_session, product)
        assert stored.emoji_match is None

    async def test_apply_emoji_for_new_products_never_raises(
        self, db_session: AsyncSession, categories
    ) -> None:
        async def boom(product_id: object) -> None:
            raise RuntimeError("nope")

        with patch.object(product_emoji, "_apply_one_on_create", new=boom):
            await product_emoji.apply_emoji_for_new_products([uuid4()])

    def test_schedule_emoji_queues_a_background_task(self) -> None:
        from fastapi import BackgroundTasks

        tasks = BackgroundTasks()
        product_emoji.schedule_emoji(tasks, [uuid4()])

        assert len(tasks.tasks) == 1

    def test_schedule_emoji_does_nothing_for_no_products(self) -> None:
        from fastapi import BackgroundTasks

        tasks = BackgroundTasks()
        product_emoji.schedule_emoji(tasks, [])

        assert len(tasks.tasks) == 0
