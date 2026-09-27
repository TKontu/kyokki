"""Q18: every product gets an icon the local model draws, safely stored.

The model writes a flat 48x48 SVG. What it answers is untrusted markup, so it is parsed with an
entity-safe parser and everything off a small allowlist is dropped before it is stored; the
iPad only ever shows it through `<img src>`. The job runs in the background, one drawing at a
time, and a failure leaves the category emoji (or the previous drawing) where it was.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.product_master import ProductMaster
from app.services import product_icons
from app.services.product_icons import (
    MAX_SVG_BYTES,
    IconModelError,
    IconRejected,
    build_prompt,
    draw_icon,
    extract_svg,
    sanitise,
)

REAL_COMPLETE = product_icons._complete

SVG_NS = "http://www.w3.org/2000/svg"
GOOD = (
    f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">'
    '<circle cx="24" cy="26" r="16" fill="#E4453A" stroke="#2B2B2B" stroke-width="2"/>'
    '<path d="M24 10 L26 4" fill="none" stroke="#5BA84A" stroke-width="2"/>'
    "</svg>"
)


def _clean(svg: str) -> str:
    return sanitise(svg)[0]


class TestSanitiseKeeps:
    def test_a_good_drawing_comes_through_unchanged(self) -> None:
        clean, changed = sanitise(GOOD)

        assert changed is False
        assert "<circle" in clean and "<path" in clean
        assert 'viewBox="0 0 48 48"' in clean

    def test_the_output_is_plain_svg_in_the_svg_namespace(self) -> None:
        clean = _clean(GOOD)

        assert clean.startswith("<svg ")
        assert f'xmlns="{SVG_NS}"' in clean
        assert "ns0:" not in clean

    def test_a_drawing_without_the_namespace_is_accepted(self) -> None:
        clean = _clean(
            '<svg viewBox="0 0 48 48"><rect x="4" y="4" width="40" height="40" fill="#F3E6C8"/></svg>'
        )

        assert "<rect" in clean
        assert f'xmlns="{SVG_NS}"' in clean

    def test_groups_and_allowed_transforms_stay(self) -> None:
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">'
            '<g transform="translate(2 3) rotate(-15, 24, 24) scale(1.5)">'
            '<ellipse cx="24" cy="24" rx="10" ry="6" fill="#F5D547"/></g></svg>'
        )

        assert changed is False
        assert 'transform="translate(2 3) rotate(-15, 24, 24) scale(1.5)"' in clean

    def test_the_viewbox_is_forced(self) -> None:
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 100 100"><circle cx="1" cy="1" r="1" fill="#FFFFFF"/></svg>'
        )

        assert changed is True
        assert 'viewBox="0 0 48 48"' in clean


class TestSanitiseRejects:
    @pytest.mark.parametrize(
        "text",
        [
            "not xml at all",
            "<svg><circle></svg>",
            f'<g xmlns="{SVG_NS}"><circle r="1"/></g>',
        ],
    )
    def test_no_parseable_svg_root_is_rejected(self, text: str) -> None:
        with pytest.raises(IconRejected):
            sanitise(text)

    def test_an_svg_left_with_only_an_empty_group_is_not_drawable(self) -> None:
        """#106 review: `<g/>` alone used to count as something drawn."""
        with pytest.raises(IconRejected):
            sanitise(
                f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48"><g><script>x</script></g></svg>'
            )

    def test_nested_empty_groups_are_not_drawable_either(self) -> None:
        with pytest.raises(IconRejected):
            sanitise(f'<svg xmlns="{SVG_NS}"><g><g/></g></svg>')

    def test_a_root_in_another_namespace_is_rejected(self) -> None:
        with pytest.raises(IconRejected):
            sanitise('<svg xmlns="http://example.com/x"><circle r="1"/></svg>')

    def test_an_oversized_result_is_rejected(self) -> None:
        shapes = "".join(
            f'<circle cx="{i % 48}" cy="{i % 48}" r="1" fill="#FFFFFF"/>'
            for i in range(400)
        )
        with pytest.raises(IconRejected):
            sanitise(f'<svg xmlns="{SVG_NS}">{shapes}</svg>')
        assert MAX_SVG_BYTES == 8192

    @pytest.mark.parametrize(
        "doctype",
        [
            '<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;">]>',
            '<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>',
            '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">',
        ],
    )
    def test_doctypes_and_entities_are_refused(self, doctype: str) -> None:
        """Billion laughs and external entities never reach the tree."""
        with pytest.raises(IconRejected):
            sanitise(
                f'{doctype}<svg xmlns="{SVG_NS}"><circle r="4" fill="#FFFFFF"/></svg>'
            )


MALICIOUS = [
    # (what the model sent, what must not survive)
    ('<script>alert(1)</script><circle r="4" fill="#FFFFFF"/>', "script"),
    ('<circle r="4" fill="#FFFFFF" onload="alert(1)"/>', "onload"),
    ('<circle r="4" fill="#FFFFFF" onclick="alert(1)"/>', "onclick"),
    ('<image href="https://evil.example/x.png"/><circle r="4"/>', "image"),
    ('<a href="javascript:alert(1)"><path d="M1 1"/></a><circle r="4"/>', "javascript"),
    ('<circle r="4" href="javascript:alert(1)"/>', "href"),
    (
        '<circle r="4" xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="#x"/>',
        "href",
    ),
    (
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject><circle r="4"/>',
        "foreignObject",
    ),
    ('<style>circle{fill:url(https://evil.example)}</style><circle r="4"/>', "style"),
    ('<circle r="4" style="fill:url(https://evil.example/x)"/>', "style"),
    ('<circle r="4" fill="url(#g)"/>', "url("),
    ('<circle r="4" fill="url(https://evil.example/x)"/>', "evil"),
    ('<circle r="4" fill="red;background:url(x)"/>', "background"),
    ('<circle r="4" class="x" id="y"/>', "class"),
    (
        '<linearGradient id="g"><stop offset="0"/></linearGradient><circle r="4"/>',
        "Gradient",
    ),
    ('<filter id="f"/><circle r="4" filter="url(#f)"/>', "filter"),
    ('<use href="#x"/><circle r="4"/>', "use"),
    (
        '<animate attributeName="href" to="javascript:alert(1)"/><circle r="4"/>',
        "animate",
    ),
    ('<set attributeName="onload" to="alert(1)"/><circle r="4"/>', "set"),
    ('<text x="1" y="1">hello</text><circle r="4"/>', "hello"),
    ('<circle r="4" transform="translate(1) url(x)"/>', "url"),
    ('<circle r="4" transform="expression(alert(1))"/>', "expression"),
    ('<circle r="4px; background: red"/>', "background"),
    ('<circle r="4" cx="javascript:1"/>', "javascript"),
    ('<path d="M0 0 L10 10 javascript:alert(1)"/><circle r="4"/>', "javascript"),
    ('<polygon points="0,0 1,1 &lt;script&gt;"/><circle r="4"/>', "script"),
    ('<circle r="4" stroke-linecap="url(x)"/>', "url"),
]


class TestMaliciousInput:
    @pytest.mark.parametrize("inner,needle", MALICIOUS)
    def test_the_dangerous_part_is_dropped(self, inner: str, needle: str) -> None:
        # A coloured shape beside the attack, so the result stays drawable and coloured.
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">{inner}'
            '<rect width="4" height="4" fill="#FFFFFF"/></svg>'
        )

        assert changed is True
        assert needle.lower() not in clean.lower()
        assert "<circle" in clean

    def test_a_namespaced_element_with_an_allowed_local_name_is_dropped(self) -> None:
        """#106 review: `<x:path>` came out as a real `<path>`."""
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">'
            '<x:path xmlns:x="http://example.com/x" d="M0 0 L48 48"/>'
            '<circle cx="24" cy="24" r="4" fill="#FFFFFF"/></svg>'
        )

        assert changed is True
        assert "<path" not in clean
        assert "M0 0 L48 48" not in clean

    def test_dropped_tail_text_marks_the_result_changed(self) -> None:
        """#106 review: text after an element was dropped without saying so."""
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">'
            '<circle cx="24" cy="24" r="4" fill="#FFFFFF"/>sneaky tail</svg>'
        )

        assert changed is True
        assert "sneaky" not in clean

    def test_root_attributes_off_the_list_are_dropped(self) -> None:
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48" onload="alert(1)" width="100%">'
            '<circle r="4" fill="#FFFFFF"/></svg>'
        )

        assert changed is True
        assert "onload" not in clean
        assert "100%" not in clean


class TestExtractSvg:
    def test_the_svg_is_cut_out_of_chatter(self) -> None:
        assert extract_svg(f"Sure! ```svg\n{GOOD}\n``` hope it helps") == GOOD

    def test_no_svg_is_none(self) -> None:
        assert extract_svg("I cannot draw that") is None

    DRAFT = f'<svg xmlns="{SVG_NS}"><rect width="1" height="1" fill="#000000"/></svg>'

    @pytest.mark.parametrize(
        "answer",
        [
            f"<think>first try: {DRAFT} hmm, no</think>\n{GOOD}",
            f"<thinking>{DRAFT}</thinking>{GOOD}",
            f"<THINK>{DRAFT}</THINK>{GOOD}",
            # The template put the opener in the prompt: only the closer is in the answer.
            f"let me sketch {DRAFT} ok</think>{GOOD}",
            f"<think>a</think><think>{DRAFT}</think>{GOOD}",
        ],
    )
    def test_a_draft_inside_the_reasoning_is_never_taken(self, answer: str) -> None:
        """Review #4: the first <svg> used to be a draft from the model's reasoning."""
        assert extract_svg(answer) == GOOD

    def test_reasoning_that_never_closes_holds_no_answer(self) -> None:
        assert extract_svg(f"<think>still thinking {self.DRAFT}") is None


class TestColourLoss:
    """Review #4: fills the sanitiser drops (names, rgb(), style) left black shapes stored."""

    @pytest.mark.parametrize(
        "inner",
        [
            '<circle cx="24" cy="24" r="16" style="fill:#E4453A;stroke:#2B2B2B"/>',
            '<circle cx="24" cy="24" r="16" fill="red" stroke="black"/>',
            '<circle cx="24" cy="24" r="16" fill="rgb(228,69,58)"/>',
            '<circle cx="24" cy="24" r="16" fill="none" stroke="none"/>',
            '<circle cx="24" cy="24" r="16"/>',
        ],
    )
    def test_no_colour_left_is_not_drawable(self, inner: str) -> None:
        with pytest.raises(IconRejected, match="no colour"):
            sanitise(f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">{inner}</svg>')

    def test_one_shape_keeping_its_colour_is_enough(self) -> None:
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">'
            '<circle cx="24" cy="24" r="16" fill="red"/>'
            '<path d="M24 10 L26 4" stroke="#5BA84A" stroke-width="2"/></svg>'
        )

        assert changed is True
        assert "#5BA84A" in clean

    def test_a_colour_on_a_group_counts(self) -> None:
        clean, _ = sanitise(
            f'<svg xmlns="{SVG_NS}"><g fill="#F5D547"><circle r="4"/></g></svg>'
        )

        assert 'fill="#F5D547"' in clean

    async def test_a_colourless_answer_is_retried_then_failed(self) -> None:
        colourless = (
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">'
            '<circle cx="24" cy="24" r="16" style="fill:#E4453A"/></svg>'
        )
        with patch.object(
            product_icons, "_complete", new=AsyncMock(side_effect=[colourless, GOOD])
        ) as model:
            svg, reasons = await product_icons._attempt("draw it")

        assert model.await_count == 2
        assert svg is not None and "#E4453A" in svg
        assert reasons == ["no colour left after sanitising"]


class TestDepth:
    def test_deep_nesting_is_rejected_not_a_recursion_error(self) -> None:
        """Review #3: a 63 KB nest of <g> raised RecursionError in the sanitiser."""
        depth = 5000
        nested = "<g>" * depth + '<circle r="4" fill="#FFFFFF"/>' + "</g>" * depth
        with pytest.raises(IconRejected, match="nested too deep"):
            sanitise(f'<svg xmlns="{SVG_NS}">{nested}</svg>')

    def test_ordinary_nesting_is_fine(self) -> None:
        nested = "<g>" * 5 + '<circle r="4" fill="#FFFFFF"/>' + "</g>" * 5
        assert "<circle" in _clean(f'<svg xmlns="{SVG_NS}">{nested}</svg>')


class TestPrompt:
    def test_it_names_the_product_the_palette_and_the_rules(self) -> None:
        prompt = build_prompt("Rye bread", "bread")

        assert "Rye bread (category: bread)" in prompt
        assert "#2B2B2B" in prompt and "#F3E6C8" in prompt
        assert 'viewBox="0 0 48 48"' in prompt

    def test_the_cooks_hint_is_added(self) -> None:
        prompt = build_prompt(
            "Karelian pasty", "bread", hint="oval rye pastry with rice filling"
        )

        assert "oval rye pastry with rice filling" in prompt

    def test_no_hint_no_hint_line(self) -> None:
        assert "cook" not in build_prompt("Tomato", "produce").lower()


# --- the job ---------------------------------------------------------------------------------


@pytest.fixture
async def categories(db_session: AsyncSession) -> None:
    from app.db.seed_categories import seed_categories

    await seed_categories(db_session)
    await db_session.commit()


@pytest.fixture(autouse=True)
def _own_session(monkeypatch: pytest.MonkeyPatch, request) -> None:
    """The job opens its own session; in a DB test it is the test's, so its rows are visible."""
    if "db_session" in request.fixturenames:
        monkeypatch.setattr(
            product_icons, "open_session", request.getfixturevalue("session_factory")
        )


@pytest.fixture
def broadcast():
    with patch(
        "app.services.product_icons.broadcast_product_update", new_callable=AsyncMock
    ) as mock:
        yield mock


async def _product(db: AsyncSession, name: str = "Tomato") -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="produce",
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
    )
    db.add(product)
    await db.commit()
    return product


async def _reload(db: AsyncSession, product: ProductMaster) -> ProductMaster:
    from sqlalchemy import select
    from sqlalchemy.orm import undefer

    return (
        await db.execute(
            select(ProductMaster)
            .where(ProductMaster.id == product.id)
            .options(undefer(ProductMaster.icon_svg))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


def _answers(*texts: str | Exception):
    return patch.object(
        product_icons, "_complete", new=AsyncMock(side_effect=list(texts))
    )


class TestDrawIcon:
    async def test_a_drawing_is_stored_and_the_product_is_ready(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with _answers(f"here you go\n{GOOD}") as model:
            await draw_icon(product.id)

        stored = await _reload(db_session, product)
        assert stored.icon_status == "ready"
        assert stored.icon_svg is not None and "<circle" in stored.icon_svg
        assert stored.icon_updated_at is not None
        assert stored.icon_version == int(stored.icon_updated_at.timestamp())
        (prompt,) = model.await_args.args
        assert "Tomato (category: produce)" in prompt
        broadcast.assert_awaited()
        assert broadcast.await_args.kwargs["action"] == "icon_updated"

    async def test_the_hint_reaches_the_model(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Karelian pasty")

        with _answers(GOOD) as model:
            await draw_icon(product.id, hint="oval rye pastry")

        assert "oval rye pastry" in model.await_args.args[0]

    async def test_a_second_attempt_follows_an_unusable_answer(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with _answers("no svg here", GOOD) as model:
            await draw_icon(product.id)

        assert model.await_count == 2
        assert (await _reload(db_session, product)).icon_status == "ready"

    async def test_two_failures_mark_it_failed_and_leave_the_emoji(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        product = await _product(db_session)

        with (
            _answers(httpx.ConnectError("down"), "<svg><g/></svg>"),
            caplog.at_level(logging.WARNING),
        ):
            await draw_icon(product.id)  # does not raise

        stored = await _reload(db_session, product)
        assert stored.icon_status == "failed"
        assert stored.icon_svg is None
        assert stored.icon_version is None

    async def test_a_failed_redraw_keeps_the_previous_drawing(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        with _answers(GOOD):
            await draw_icon(product.id)
        before = await _reload(db_session, product)
        version = before.icon_version

        with _answers("nope", "still nope"):
            await draw_icon(product.id)

        after = await _reload(db_session, product)
        assert after.icon_status == "failed"
        assert after.icon_svg is not None and "<circle" in after.icon_svg
        assert after.icon_version == version

    async def test_a_drawing_the_cook_dropped_meanwhile_is_discarded(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        async def cook_clears_it(prompt: str) -> str:
            await product_icons.clear_icon(db_session, product.id)
            return GOOD

        with patch.object(product_icons, "_complete", new=cook_clears_it):
            await draw_icon(product.id)

        stored = await _reload(db_session, product)
        assert stored.icon_status == "cleared"
        assert stored.icon_svg is None

    async def test_a_product_the_cook_gave_the_emoji_is_not_drawn(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        await product_icons.clear_icon(db_session, product.id)

        with _answers(GOOD) as model:
            await draw_icon(product.id)

        model.assert_not_awaited()

    async def test_a_product_that_is_gone_is_skipped(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        with _answers(GOOD) as model:
            await draw_icon(uuid4())

        model.assert_not_awaited()

    async def test_anything_going_wrong_never_escapes(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with _answers(RuntimeError("boom"), RuntimeError("boom")):
            await draw_icon(product.id)

    async def test_the_svg_body_and_the_prompt_are_not_logged_at_info(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        product = await _product(db_session, "Secret sauce")

        with _answers(GOOD), caplog.at_level(logging.INFO):
            await draw_icon(product.id, hint="very private hint")

        text = " ".join(
            f"{r.getMessage()} {r.__dict__}"
            for r in caplog.records
            if r.levelno >= logging.INFO
        )
        assert "<svg" not in text and "<circle" not in text
        assert "very private hint" not in text
        assert "Draw a flat icon" not in text


class TestOneAtATime:
    async def test_jobs_never_overlap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        running = 0
        most = 0

        async def slow(product_id, hint):
            nonlocal running, most
            running += 1
            most = max(most, running)
            await asyncio.sleep(0.01)
            running -= 1

        monkeypatch.setattr(product_icons, "_draw", slow)

        await asyncio.gather(*(draw_icon(uuid4()) for _ in range(4)))

        assert most == 1


def _gateway(monkeypatch: pytest.MonkeyPatch, respond) -> dict:
    """Route the real `_complete` to a fake gateway; returns what it saw."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return respond(request)

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def client(**kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return real(transport=transport)

    monkeypatch.setattr(product_icons.httpx, "AsyncClient", client)
    return seen


def _answer(content) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


class TestTheGatewayCall:
    """The real `_complete` (the conftest stubs it for every other test)."""

    async def test_it_uses_the_icon_model_timeout_key_and_token_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _gateway(monkeypatch, lambda request: _answer(GOOD))
        monkeypatch.setattr(settings, "ICON_MODEL", "c2.some-model")
        monkeypatch.setattr(settings, "ICON_TIMEOUT", 321.0)
        monkeypatch.setattr(settings, "LLM_API_KEY", "the-key")
        monkeypatch.setattr(settings, "LLM_MAX_TOKENS", 1234)

        assert await REAL_COMPLETE("draw it") == GOOD
        assert seen["url"].endswith("/chat/completions")
        assert seen["headers"]["authorization"] == "Bearer the-key"
        assert seen["body"]["model"] == "c2.some-model"
        assert seen["body"]["messages"] == [{"role": "user", "content": "draw it"}]
        assert seen["body"]["max_tokens"] == 1234
        assert seen["body"]["temperature"] == 0.2
        assert "chat_template_kwargs" not in seen["body"]
        assert seen["timeout"] == 321.0

    async def test_muse_glimmer_gets_its_reasoning_strength(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _gateway(monkeypatch, lambda request: _answer(GOOD))
        monkeypatch.setattr(settings, "ICON_MODEL", "c2.muse-glimmer")
        monkeypatch.setattr(settings, "LLM_REASONING_STRENGTH", "medium")

        await REAL_COMPLETE("draw it")

        assert seen["body"]["chat_template_kwargs"] == {"reasoning_strength": "medium"}

    async def test_muse_glimmer_without_a_strength_sends_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _gateway(monkeypatch, lambda request: _answer(GOOD))
        monkeypatch.setattr(settings, "ICON_MODEL", "c2.muse-glimmer")
        monkeypatch.setattr(settings, "LLM_REASONING_STRENGTH", None)

        await REAL_COMPLETE("draw it")

        assert "chat_template_kwargs" not in seen["body"]

    @pytest.mark.parametrize(
        "respond",
        [
            lambda request: httpx.Response(503, json={"error": "busy"}),
            lambda request: httpx.Response(200, content=b"not json"),
            lambda request: httpx.Response(200, json={"choices": []}),
            lambda request: httpx.Response(200, json={"no": "choices"}),
            lambda request: httpx.Response(200, json={"choices": [{"message": None}]}),
        ],
        ids=["503", "bad-json", "no-choices", "no-choices-key", "no-message"],
    )
    async def test_a_bad_response_is_an_icon_model_error(
        self, monkeypatch: pytest.MonkeyPatch, respond
    ) -> None:
        _gateway(monkeypatch, respond)

        with pytest.raises(IconModelError):
            await REAL_COMPLETE("draw it")

    async def test_an_unreachable_gateway_is_an_icon_model_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        _gateway(monkeypatch, down)

        with pytest.raises(IconModelError):
            await REAL_COMPLETE("draw it")

    async def test_empty_content_is_an_empty_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _gateway(monkeypatch, lambda request: _answer(None))

        assert await REAL_COMPLETE("draw it") == ""


class TestTestsNeverReachTheGateway:
    """Review #1: a test that committed for real sent drawings to the homelab gateway."""

    def test_the_conftest_stubs_the_drawing_call(self) -> None:
        assert product_icons._complete is not REAL_COMPLETE

    async def test_a_job_without_its_own_stub_sends_nothing(
        self,
        db_session: AsyncSession,
        categories,
        broadcast,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        attempted: list[str] = []

        async def refuse(self, request, **kwargs):
            attempted.append(str(request.url))
            raise AssertionError(f"a test tried to reach {request.url}")

        monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
        product = await _product(db_session)

        await draw_icon(product.id)

        assert attempted == []
        assert (await _reload(db_session, product)).icon_status == "failed"


class TestNeverPendingForever:
    """Review #3: anything breaking after `pending` was committed left it there for good."""

    async def test_a_sanitiser_crash_ends_failed(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with (
            _answers(GOOD, GOOD),
            patch.object(product_icons, "sanitise", side_effect=RecursionError()),
        ):
            await draw_icon(product.id)  # does not raise

        assert (await _reload(db_session, product)).icon_status == "failed"

    async def test_a_database_error_storing_it_ends_failed_and_keeps_the_old_one(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        with _answers(GOOD):
            await draw_icon(product.id)
        version = (await _reload(db_session, product)).icon_version

        with (
            _answers(GOOD),
            patch.object(
                product_icons.crud_product,
                "store_icon",
                side_effect=RuntimeError("connection lost"),
            ),
        ):
            await draw_icon(product.id)

        after = await _reload(db_session, product)
        assert after.icon_status == "failed"
        assert after.icon_svg is not None and after.icon_version == version

    async def test_a_stale_pending_is_picked_up_again(
        self, db_session: AsyncSession, categories
    ) -> None:
        stale = await _product(db_session, "Stale")
        fresh = await _product(db_session, "Fresh")
        long_ago = datetime.now(UTC) - timedelta(seconds=2 * settings.ICON_TIMEOUT + 60)
        stale.icon_status = "pending"  # type: ignore[assignment]
        stale.updated_at = long_ago  # type: ignore[assignment]
        fresh.icon_status = "pending"  # type: ignore[assignment]
        await db_session.commit()

        picked = await product_icons.products_to_draw(db_session)

        assert [p.id for p in picked] == [stale.id]
        assert await product_icons.still_needs_drawing(db_session, stale.id)
        assert not await product_icons.still_needs_drawing(db_session, fresh.id)

    async def test_a_stale_pending_can_be_drawn(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        product.icon_status = "pending"  # type: ignore[assignment]
        product.updated_at = datetime.now(UTC) - timedelta(days=1)  # type: ignore[assignment]
        await db_session.commit()

        with _answers(GOOD):
            await draw_icon(product.id)

        assert (await _reload(db_session, product)).icon_status == "ready"


class TestTheDatabaseLock:
    """Review #6: two API workers and the backfill script draw one at a time between them."""

    async def test_the_gateway_call_holds_the_advisory_lock(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        held: list[int] = []

        async def count_locks() -> int:
            return int(
                await db_session.scalar(
                    text(
                        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                        "AND objid = :key AND granted"
                    ),
                    {"key": product_icons.ICON_LOCK_KEY},
                )
            )

        async def draw(prompt: str) -> str:
            held.append(await count_locks())
            return GOOD

        with patch.object(product_icons, "_complete", new=draw):
            await draw_icon(product.id)

        assert held == [1]
        assert await count_locks() == 0

    async def test_the_lock_is_released_when_the_call_breaks(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with patch.object(
            product_icons, "_attempt", new=AsyncMock(side_effect=RuntimeError("boom"))
        ):
            await draw_icon(product.id)

        count = await db_session.scalar(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND objid = :key AND granted"
            ),
            {"key": product_icons.ICON_LOCK_KEY},
        )
        assert count == 0
        assert (await _reload(db_session, product)).icon_status == "failed"


def test_the_settings_have_defaults() -> None:
    assert settings.ICON_MODEL.startswith("c2.")
    assert settings.ICON_TIMEOUT == 600.0


def test_an_aware_timestamp_gives_whole_seconds() -> None:
    product = ProductMaster(
        icon_updated_at=datetime(2026, 9, 26, 12, 0, 0, 500000, tzinfo=UTC)
    )

    assert product.icon_version == int(
        datetime(2026, 9, 26, 12, tzinfo=UTC).timestamp()
    )


class TestBackfill:
    async def test_never_drawn_failed_and_stale_are_picked_oldest_first(
        self, db_session: AsyncSession, categories
    ) -> None:
        never = await _product(db_session, "Never drawn")
        failed = await _product(db_session, "Failed")
        failed.icon_status = "failed"  # type: ignore[assignment]
        for name, status in (
            ("Ready", "ready"),
            ("Cleared", "cleared"),
            ("Busy", "pending"),
        ):
            other = await _product(db_session, name)
            other.icon_status = status  # type: ignore[assignment]
        await db_session.commit()

        picked = await product_icons.products_to_draw(db_session)

        assert [p.id for p in picked] == [never.id, failed.id]

    async def test_the_limit_caps_it(
        self, db_session: AsyncSession, categories
    ) -> None:
        for name in ("A", "B", "C"):
            await _product(db_session, name)

        assert len(await product_icons.products_to_draw(db_session, limit=2)) == 2

    async def test_it_skips_what_changed_since_the_list_was_read(
        self, db_session: AsyncSession, categories, session_factory
    ) -> None:
        """Review #8: the list was read once, so it redrew what the API had just drawn."""
        from scripts.backfill_icons import backfill

        first = await _product(db_session, "First")
        drawn_meanwhile = await _product(db_session, "Drawn by the API")
        cleared_meanwhile = await _product(db_session, "Cleared by the cook")
        started_meanwhile = await _product(db_session, "Started by the API")
        drawn: list = []

        async def draw(product_id, hint=None):
            drawn.append(product_id)
            # While the first one is drawn, the API and the cook get to the others.
            for product, status in (
                (first, "ready"),
                (drawn_meanwhile, "ready"),
                (cleared_meanwhile, "cleared"),
                (started_meanwhile, "pending"),
            ):
                product.icon_status = status  # type: ignore[assignment]
            await db_session.commit()

        with patch.object(product_icons, "draw_icon", new=draw):
            counts = await backfill(None, False, sessions=session_factory)

        assert drawn == [first.id]
        assert counts == {"ready": 1, "failed": 0, "skipped": 3}

    async def test_a_dry_run_draws_nothing(
        self, db_session: AsyncSession, categories, session_factory
    ) -> None:
        from scripts.backfill_icons import backfill

        await _product(db_session)

        with patch.object(product_icons, "draw_icon", new=AsyncMock()) as draw:
            counts = await backfill(None, True, sessions=session_factory)

        draw.assert_not_awaited()
        assert counts == {"ready": 0, "failed": 0, "skipped": 0}

    async def test_it_counts_a_failed_drawing(
        self, db_session: AsyncSession, categories, session_factory, broadcast
    ) -> None:
        from scripts.backfill_icons import backfill

        product = await _product(db_session)

        counts = await backfill(None, False, sessions=session_factory)  # stub: nothing

        assert counts == {"ready": 0, "failed": 1, "skipped": 0}
        assert (await _reload(db_session, product)).icon_status == "failed"
