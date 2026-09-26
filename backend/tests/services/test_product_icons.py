"""Q18: every product gets an icon the local model draws, safely stored.

The model writes a flat 48x48 SVG. What it answers is untrusted markup, so it is parsed with an
entity-safe parser and everything off a small allowlist is dropped before it is stored; the
iPad only ever shows it through `<img src>`. The job runs in the background, one drawing at a
time, and a failure leaves the category emoji (or the previous drawing) where it was.
"""

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.product_master import ProductMaster
from app.services import product_icons
from app.services.product_icons import (
    MAX_SVG_BYTES,
    IconRejected,
    build_prompt,
    draw_icon,
    extract_svg,
    sanitise,
)

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
        clean, changed = sanitise(
            f'<svg xmlns="{SVG_NS}" viewBox="0 0 48 48">{inner}</svg>'
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


class TestTheGatewayCall:
    async def test_it_uses_the_icon_model_and_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": GOOD}}]}
            )

        transport = httpx.MockTransport(handler)
        real = httpx.AsyncClient

        def client(**kwargs):
            seen["timeout"] = kwargs.get("timeout")
            return real(transport=transport)

        monkeypatch.setattr(product_icons.httpx, "AsyncClient", client)
        monkeypatch.setattr(settings, "ICON_MODEL", "c2.some-model")
        monkeypatch.setattr(settings, "ICON_TIMEOUT", 321.0)

        assert await product_icons._complete("draw it") == GOOD
        assert seen["url"].endswith("/chat/completions")
        assert seen["body"]["model"] == "c2.some-model"
        assert seen["body"]["messages"] == [{"role": "user", "content": "draw it"}]
        assert "chat_template_kwargs" not in seen["body"]
        assert seen["timeout"] == 321.0


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


class TestBackfillSelection:
    async def test_never_drawn_and_failed_are_picked_oldest_first(
        self, db_session: AsyncSession, categories
    ) -> None:
        from scripts.backfill_icons import products_to_draw

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

        picked = await products_to_draw(db_session)

        assert [row[0] for row in picked] == [never.id, failed.id]

    async def test_the_limit_caps_it(
        self, db_session: AsyncSession, categories
    ) -> None:
        from scripts.backfill_icons import products_to_draw

        for name in ("A", "B", "C"):
            await _product(db_session, name)

        assert len(await products_to_draw(db_session, limit=2)) == 2
