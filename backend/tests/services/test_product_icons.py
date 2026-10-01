"""Q18-G2: generated product icons replace the rejected SVG drawer.

A food product with no exact or cook-chosen emoji (the "gap") gets a flat icon through
ComfyUI (`services/comfyui.py`, `services/icon_workflow.py`), downscaled with Pillow and
stored with the product as a small transparent PNG. The job runs in the background, one
render at a time, and a failure leaves whatever image was there before (or none) where it was.
"""

import asyncio
import io
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import settings
from app.models.product_master import EmojiMatch, IconStatus, ProductMaster
from app.services import comfyui, product_icons
from app.services.non_food import remember_non_food
from app.services.product_icons import (
    draw_icon,
    draw_icons,
    icon_subject,
    schedule_icons,
)


def _png(
    colour: tuple[int, int, int, int] = (228, 69, 58, 255), size: int = 8
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), colour).save(buffer, format="PNG")
    return buffer.getvalue()


GOOD = _png()


class TestIconSubject:
    def test_a_plain_name_has_no_brief(self) -> None:
        assert icon_subject("Quark") == "Quark"

    def test_a_gap_product_with_a_brief_gets_it_appended(self) -> None:
        subject = icon_subject("Tomato puree")

        assert subject == "Tomato puree, a small can or squeeze-out tube"

    def test_the_brief_lookup_is_case_and_space_insensitive(self) -> None:
        # The name keeps its own casing in the subject; only the brief lookup is folded.
        assert "a can, not a fresh tomato" in icon_subject("  canned   TOMATOES ")

    def test_the_cooks_hint_is_appended_last(self) -> None:
        subject = icon_subject("Tomato puree", hint="in a yellow tube")

        assert subject == (
            "Tomato puree, a small can or squeeze-out tube, in a yellow tube"
        )

    def test_a_blank_hint_is_ignored(self) -> None:
        assert icon_subject("Quark", hint="   ") == "Quark"


# --- scheduling --------------------------------------------------------------------------


class TestScheduleIcons:
    def test_no_products_schedules_nothing(self) -> None:
        tasks = BackgroundTasks()

        schedule_icons(tasks, [])

        assert tasks.tasks == []

    def test_it_always_queues_draw_icons_whatever_comfyui_is_set_to(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`services/shelf_life_on_create.py` (a sibling lane) schedules and identifies this
        task by name; `schedule_icons` itself must not skip queuing it, disabled or not."""
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        tasks = BackgroundTasks()
        ids = [uuid4(), uuid4()]

        schedule_icons(tasks, ids, "a hint")

        (task,) = [t for t in tasks.tasks if t.func is draw_icons]
        assert list(task.args[0]) == ids
        assert task.args[1] == "a hint"


class TestDrawIconsWhenDisabled:
    """`COMFYUI_BASE_URL` empty: the one place generation actually refuses to run."""

    async def test_it_touches_no_product_and_calls_comfyui_never(
        self, db_session: AsyncSession, categories, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        render = AsyncMock(return_value=[GOOD])
        monkeypatch.setattr(product_icons.comfyui, "render", render)
        product = await _product(db_session)

        await draw_icons([product.id])

        render.assert_not_awaited()
        assert (await _reload(db_session, product)).icon_status is None

    async def test_it_logs_once_for_the_whole_batch_not_per_product(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "")
        ids = [uuid4(), uuid4(), uuid4()]

        with caplog.at_level(logging.INFO):
            await draw_icons(ids)

        disabled_lines = [
            r for r in caplog.records if "disabled" in r.getMessage().lower()
        ]
        assert len(disabled_lines) == 1


# --- the job -------------------------------------------------------------------------------


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


@pytest.fixture(autouse=True)
def _comfyui_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test below is about what happens once generation IS configured; the dedicated
    disabled-path tests above set `COMFYUI_BASE_URL` back to empty themselves."""
    monkeypatch.setattr(settings, "COMFYUI_BASE_URL", "http://comfyui.test")


@pytest.fixture
def broadcast():
    with patch(
        "app.services.product_icons.broadcast_product_update", new_callable=AsyncMock
    ) as mock:
        yield mock


async def _product(
    db: AsyncSession,
    name: str = "Tomato",
    *,
    emoji_match: EmojiMatch | None = None,
    icon_status: IconStatus | None = None,
) -> ProductMaster:
    product = ProductMaster(
        id=uuid4(),
        canonical_name=name,
        category="produce",
        storage_type="refrigerator",
        default_shelf_life_days=10,
        unit_type="count",
        default_unit="pcs",
        emoji_match=emoji_match.value if emoji_match else None,
        icon_status=icon_status.value if icon_status else None,
    )
    db.add(product)
    await db.commit()
    return product


async def _reload(db: AsyncSession, product: ProductMaster) -> ProductMaster:
    return (
        await db.execute(
            select(ProductMaster)
            .where(ProductMaster.id == product.id)
            .options(undefer(ProductMaster.icon_image))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


def _render(*, images=None, error: Exception | None = None):
    if error is not None:
        return patch.object(
            product_icons.comfyui, "render", new=AsyncMock(side_effect=error)
        )
    return patch.object(
        product_icons.comfyui,
        "render",
        new=AsyncMock(return_value=[GOOD] if images is None else images),
    )


class TestDrawIcon:
    async def test_an_image_is_stored_and_the_product_is_ready(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with _render() as render:
            await draw_icon(product.id)

        stored = await _reload(db_session, product)
        assert stored.icon_status == "ready"
        assert stored.icon_image is not None
        assert stored.icon_seed is not None
        assert stored.icon_updated_at is not None
        assert stored.icon_version == int(stored.icon_updated_at.timestamp())
        (workflow,), kwargs = render.await_args
        assert "Tomato" in workflow["3"]["inputs"]["text"]
        assert workflow["6"]["inputs"]["seed"] == stored.icon_seed
        broadcast.assert_awaited()
        assert broadcast.await_args.kwargs["action"] == "icon_updated"

    async def test_the_image_is_downscaled_to_the_configured_size(
        self,
        db_session: AsyncSession,
        categories,
        broadcast,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ICON_IMAGE_SIZE", 32)
        product = await _product(db_session)

        with _render(images=[_png(size=1024)]):
            await draw_icon(product.id)

        stored = await _reload(db_session, product)
        with Image.open(io.BytesIO(stored.icon_image)) as image:
            assert image.size == (32, 32)
            assert image.mode == "RGBA"

    async def test_the_hint_reaches_the_subject(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, "Karelian pasty")

        with _render() as render:
            await draw_icon(product.id, hint="oval rye pastry")

        (workflow,), _ = render.await_args
        assert "oval rye pastry" in workflow["3"]["inputs"]["text"]

    async def test_a_render_failure_marks_it_failed_and_leaves_the_emoji(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        product = await _product(db_session)

        with (
            _render(error=comfyui.ComfyUITimeout("too slow")),
            caplog.at_level(logging.WARNING),
        ):
            await draw_icon(product.id)  # does not raise

        stored = await _reload(db_session, product)
        assert stored.icon_status == "failed"
        assert stored.icon_image is None
        assert stored.icon_version is None

    async def test_a_failed_regenerate_keeps_the_previous_image(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        with _render():
            await draw_icon(product.id)
        before = await _reload(db_session, product)
        version = before.icon_version
        image = before.icon_image

        with _render(error=comfyui.ComfyUIError("failed")):
            await draw_icon(product.id)

        after = await _reload(db_session, product)
        assert after.icon_status == "failed"
        assert after.icon_image == image
        assert after.icon_version == version

    async def test_an_empty_output_list_is_treated_as_a_failure(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with _render(images=[]):
            await draw_icon(product.id)

        assert (await _reload(db_session, product)).icon_status == "failed"

    async def test_an_image_the_cook_cleared_meanwhile_is_discarded(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        async def cook_clears_it(workflow, **kwargs):
            await product_icons.clear_icon(db_session, product.id)
            return [GOOD]

        with patch.object(product_icons.comfyui, "render", new=cook_clears_it):
            await draw_icon(product.id)

        stored = await _reload(db_session, product)
        assert stored.icon_status == "cleared"
        assert stored.icon_image is None

    async def test_a_product_that_is_gone_is_skipped(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        with _render() as render:
            await draw_icon(uuid4())

        render.assert_not_awaited()

    async def test_anything_going_wrong_never_escapes(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with _render(error=RuntimeError("boom")):
            await draw_icon(product.id)  # does not raise

    async def test_the_hint_and_the_image_bytes_are_not_logged_at_info(
        self, db_session: AsyncSession, categories, broadcast, caplog
    ) -> None:
        product = await _product(db_session, "Secret sauce")

        with _render(), caplog.at_level(logging.INFO):
            await draw_icon(product.id, hint="very private hint")

        text = " ".join(
            f"{r.getMessage()} {r.__dict__}"
            for r in caplog.records
            if r.levelno >= logging.INFO
        )
        assert "very private hint" not in text
        assert GOOD.hex() not in text


class TestAutomaticQueueGating:
    """Automatic scheduling (a new product, or a rename) never generates for cleared, an
    exact/cook emoji, or non-food - `draw_icon` is the only place with a database session to
    check, so the gate lives at the top of the job itself."""

    async def test_a_cleared_product_is_never_generated(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, icon_status=IconStatus.CLEARED)

        with _render() as render:
            await draw_icon(product.id)

        render.assert_not_awaited()
        assert (await _reload(db_session, product)).icon_status == "cleared"

    async def test_an_exact_emoji_product_is_never_generated(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, emoji_match=EmojiMatch.EXACT)

        with _render() as render:
            await draw_icon(product.id)

        render.assert_not_awaited()

    async def test_a_cook_chosen_emoji_product_is_never_generated(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, emoji_match=EmojiMatch.COOK)

        with _render() as render:
            await draw_icon(product.id)

        render.assert_not_awaited()

    async def test_a_proposed_or_none_emoji_product_is_still_generated(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        cases = [
            ("Pomegranate", EmojiMatch.PROPOSED),
            ("Lingonberries", EmojiMatch.NONE),
            ("Raspberries", None),
        ]
        for name, match in cases:
            product = await _product(db_session, name, emoji_match=match)

            with _render() as render:
                await draw_icon(product.id)

            render.assert_awaited_once()

    async def test_a_non_food_name_is_never_generated(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        product = await _product(db_session, "Toilet paper")

        with _render() as render:
            await draw_icon(product.id)

        render.assert_not_awaited()
        assert (await _reload(db_session, product)).icon_status is None


class TestRegenerateIsExplicit:
    """`request_redraw` marks the product `pending` with a fresh seed before the job runs;
    that mark is what tells `draw_icon` this is the cook's own ask, not the automatic queue."""

    async def test_regenerate_still_renders_for_an_exact_emoji_product(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, emoji_match=EmojiMatch.EXACT)
        await product_icons.request_redraw(db_session, product.id)

        with _render() as render:
            await draw_icon(product.id)

        render.assert_awaited_once()
        assert (await _reload(db_session, product)).icon_status == "ready"

    async def test_regenerate_still_renders_for_a_cleared_product(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session, icon_status=IconStatus.CLEARED)
        await product_icons.request_redraw(db_session, product.id)

        with _render() as render:
            await draw_icon(product.id)

        render.assert_awaited_once()
        assert (await _reload(db_session, product)).icon_status == "ready"

    async def test_regenerate_uses_the_seed_it_already_picked(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        pending = await product_icons.request_redraw(db_session, product.id)
        picked_seed = pending.icon_seed

        with _render() as render:
            await draw_icon(product.id)

        (workflow,), _ = render.await_args
        assert workflow["6"]["inputs"]["seed"] == picked_seed
        assert (await _reload(db_session, product)).icon_seed == picked_seed

    async def test_regenerate_is_never_stuck_pending_for_a_non_food_name(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        product = await _product(db_session, "Toilet paper")
        await product_icons.request_redraw(db_session, product.id)

        with _render() as render:
            await draw_icon(product.id)

        render.assert_not_awaited()
        assert (await _reload(db_session, product)).icon_status == "failed"
        broadcast.assert_awaited()


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

        monkeypatch.setattr(product_icons, "_generate", slow)

        await asyncio.gather(*(draw_icon(uuid4()) for _ in range(4)))

        assert most == 1


class TestNeverPendingForever:
    async def test_a_downscale_crash_ends_failed(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)

        with (
            _render(),
            patch.object(product_icons, "_downscale", side_effect=RuntimeError()),
        ):
            await draw_icon(product.id)  # does not raise

        assert (await _reload(db_session, product)).icon_status == "failed"

    async def test_a_database_error_storing_it_ends_failed_and_keeps_the_old_image(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        with _render():
            await draw_icon(product.id)
        version = (await _reload(db_session, product)).icon_version

        with (
            _render(),
            patch.object(
                product_icons.crud_product,
                "store_icon",
                side_effect=RuntimeError("connection lost"),
            ),
        ):
            await draw_icon(product.id)

        after = await _reload(db_session, product)
        assert after.icon_status == "failed"
        assert after.icon_image is not None and after.icon_version == version

    async def test_a_stale_pending_is_picked_up_again(
        self, db_session: AsyncSession, categories
    ) -> None:
        stale = await _product(db_session, "Stale")
        fresh = await _product(db_session, "Fresh")
        long_ago = datetime.now(UTC) - timedelta(
            seconds=2 * settings.COMFYUI_TIMEOUT + 60
        )
        stale.icon_status = "pending"  # type: ignore[assignment]
        stale.updated_at = long_ago  # type: ignore[assignment]
        fresh.icon_status = "pending"  # type: ignore[assignment]
        await db_session.commit()

        picked = await product_icons.products_to_generate(db_session)

        assert [p.id for p in picked] == [stale.id]
        assert await product_icons.still_needs_generation(db_session, stale.id)
        assert not await product_icons.still_needs_generation(db_session, fresh.id)

    async def test_a_stale_pending_can_be_generated(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        product.icon_status = "pending"  # type: ignore[assignment]
        product.updated_at = datetime.now(UTC) - timedelta(days=1)  # type: ignore[assignment]
        await db_session.commit()

        with _render():
            await draw_icon(product.id)

        assert (await _reload(db_session, product)).icon_status == "ready"


class TestProductsToGenerate:
    async def test_a_non_food_gap_product_is_excluded(
        self, db_session: AsyncSession, categories
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        await _product(db_session, "Toilet paper")
        food = await _product(db_session, "Quark")

        picked = await product_icons.products_to_generate(db_session)

        assert [p.id for p in picked] == [food.id]

    async def test_an_exact_or_cook_emoji_product_is_excluded(
        self, db_session: AsyncSession, categories
    ) -> None:
        await _product(db_session, "Gouda", emoji_match=EmojiMatch.EXACT)
        await _product(db_session, "Ketchup", emoji_match=EmojiMatch.COOK)
        gap = await _product(db_session, "Quark", emoji_match=EmojiMatch.NONE)

        picked = await product_icons.products_to_generate(db_session)

        assert [p.id for p in picked] == [gap.id]

    async def test_a_cleared_product_is_excluded(
        self, db_session: AsyncSession, categories
    ) -> None:
        await _product(db_session, "Quark", icon_status=IconStatus.CLEARED)

        assert await product_icons.products_to_generate(db_session) == []

    async def test_the_limit_is_honoured_after_filtering_non_food(
        self, db_session: AsyncSession, categories
    ) -> None:
        await remember_non_food(db_session, "S-Market", ["Toilet paper"])
        await _product(db_session, "Toilet paper")
        await _product(db_session, "Quark")
        await _product(db_session, "Skyr")

        picked = await product_icons.products_to_generate(db_session, limit=1)

        assert len(picked) == 1


class TestClearAndStoredIcon:
    async def test_clear_icon_drops_the_image_and_seed(
        self, db_session: AsyncSession, categories, broadcast
    ) -> None:
        product = await _product(db_session)
        with _render():
            await draw_icon(product.id)

        cleared = await product_icons.clear_icon(db_session, product.id)

        assert cleared is not None
        assert cleared.icon_status == "cleared"
        assert await product_icons.stored_icon(db_session, product.id) is None

    async def test_clear_icon_on_an_unknown_product_is_none(
        self, db_session: AsyncSession, categories
    ) -> None:
        assert await product_icons.clear_icon(db_session, uuid4()) is None

    async def test_stored_icon_is_none_before_generation(
        self, db_session: AsyncSession, categories
    ) -> None:
        product = await _product(db_session)

        assert await product_icons.stored_icon(db_session, product.id) is None
