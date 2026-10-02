"""Generated product icons (Q18-G2): a ComfyUI render for the "gap".

Q18's spike had the local model draw an SVG icon per product; the operator rejected every one
of them on 2026-09-27 (docs/spikes/Q18_icon_styles.md) and asked for the drawings cleared. In
its place, the operator ruled (2026-09-30) that **generation is for the gap only** - a food
product whose tile does not already show an exact or cook-chosen Apple emoji
(`product_master.emoji_match`, Q18 build) - through the frozen ComfyUI graph built in Q18-G1
(`services/comfyui.py`, `services/icon_workflow.py`): SDXL + a flat-icon LoRA + BiRefNet
background removal, 1024x1024, one image. Non-food never gets one.

The 1024x1024 output is downscaled with Pillow to `settings.ICON_IMAGE_SIZE` (sharp on the
iPad tile, small to store) and kept as the product's `icon_image`, a transparent PNG, with the
seed that produced it (`icon_seed`) and a status exactly like the rejected drawer's
(`icon_status`: pending, ready, failed, cleared) - the operator's 2026-09-26 storage ruling
was "the icon lives with the product", which this keeps.

A render takes seconds to minutes and the GPU host is shared, so it runs as a background job
after the response has gone, one at a time across every process (API workers and the backfill
script) on a Postgres advisory lock - the client itself only ever serialises one job per
process (`comfyui.py`'s own lock), not across the two API workers. A failure keeps whatever
image was there before (or none) and marks `failed`, with no retry loop; a `pending` whose job
died counts as stale after twice `COMFYUI_TIMEOUT`, so the backfill tries it again.

Automatic scheduling (a new product, or one just renamed) is gated at generation time -
`icon_needs_generation` skips `cleared` and an exact/cook emoji, and a non-food name is always
skipped - because nothing here has a database session at schedule time to check first. A
cook's own **Regenerate**, already marked `pending` with a fresh seed before the job runs
(`request_redraw`), is not second-guessed on `cleared`: asking to regenerate is how the cook
un-clears one. An exact or cook emoji is never bypassed either way, explicit or not (F5,
planner ruling) - `request_redraw` refuses it with 409 before ever marking pending, so the
cook sees it as "clear the emoji first", not a silent no-op. Non-food is the same absolute
rule it always was. Both refusals resolve the row (`failed`) instead of leaving it hanging on
"Generating...", for the same reason: a `pending` row some other path ever left behind must
never wait forever for a job that will not run.

`schedule_icons` always queues its background task (`draw_icons`, the same name and call shape
Q18's drawer used - `services/shelf_life_on_create.py` and its tests, a sibling lane, schedule
and identify it by that name and are not this lane's to rename). With `COMFYUI_BASE_URL`
empty, `draw_icons` itself refuses at the top, before touching the database or any product in
the batch - one INFO line per call, not one per product - so nothing is actually queued or
retried in any sense that matters: no row is written, no GPU is asked. Nothing in the receipt
or stock path waits for an icon.
"""

from __future__ import annotations

import asyncio
import io
import random
import time
import weakref
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import BackgroundTasks
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.config import settings
from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.models.product_master import EmojiMatch, IconStatus, ProductMaster
from app.services import comfyui
from app.services.broadcast_helpers import broadcast_product_update
from app.services.icon_briefs import brief_for
from app.services.icon_workflow import build_icon_workflow
from app.services.product_emoji import is_non_food

logger = get_logger(__name__)

# The Postgres advisory lock every process takes around a render: any fixed 64-bit number.
# Different from Q18's SVG-drawing lock (0x4B794F18) so the two can never collide if both
# were ever somehow live at once.
ICON_LOCK_KEY = 0x4B794F19  # "KyO" + Q18-G2
STALE_AFTER_TIMEOUTS = (
    2  # a pending older than this many COMFYUI_TIMEOUTs has no live job
)
# How often a job that lost the race for the render lock checks again (F10 review).
LOCK_POLL_INTERVAL = 2.0
# `icon_workflow.SEED_MAX` is ComfyUI's full unsigned 64-bit range, but `icon_seed` is a
# Postgres BIGINT (signed 64-bit): a seed this module picks itself never exceeds that
# column's range, whatever an explicit seed passed straight to `build_icon_workflow` may be.
RANDOM_SEED_MAX = 2**63 - 1


# --- the generation subject --------------------------------------------------------------


def icon_subject(name: str, hint: str | None = None) -> str:
    """What to ask ComfyUI to draw: the generic name, the operator's brief, the cook's hint.

    `app.services.icon_briefs` is the only source of the operator's own words for a gap
    product ("a small can or squeeze out tube" for Tomato puree); most gap products have none
    and generate from their name alone. A cook's Regenerate hint, if given, is appended last.
    """
    parts = [name]
    brief = brief_for(name)
    if brief:
        parts.append(brief)
    if hint and hint.strip():
        parts.append(hint.strip())
    return ", ".join(parts)


# --- eligibility ----------------------------------------------------------------------------


def _emoji_already_shown(product: ProductMaster) -> bool:
    """An exact or cook-chosen emoji already wins the tile (lib/productIcon.ts's precedence).

    Never overridden, explicit Regenerate or not (F5, planner ruling): the image could never
    show. `request_redraw` already refuses this with 409 before ever marking the product
    pending, so a job reaching this check still true is the last line of defense, not the
    usual path.
    """
    return product.emoji_match in (EmojiMatch.EXACT, EmojiMatch.COOK)


async def still_needs_generation(db: AsyncSession, product_id: UUID) -> bool:
    """Re-check one product right before generating it: another job may have got there first."""
    product = await crud_product.get_icon_subject(db, product_id)
    if product is None:
        return False
    if not crud_product.icon_needs_generation(product, stale_before()):
        return False
    return not await is_non_food(db, str(product.canonical_name))


# --- the job ---------------------------------------------------------------------------------


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    """A session of the job's own. Looked up at call time, so the tests can rebind it."""
    return app_session.AsyncSessionLocal()


def stale_before() -> datetime:
    """A `pending` older than this has no live job behind it (a restart, a crash)."""
    return datetime.now(UTC) - timedelta(
        seconds=STALE_AFTER_TIMEOUTS * settings.COMFYUI_TIMEOUT
    )


# One lock per event loop keeps this process's jobs in order; the app runs one loop, so this is
# process-wide there. Keyed by loop so a lock never outlives the loop it was bound to.
_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _job_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


@asynccontextmanager
async def _gateway_turn() -> AsyncIterator[None]:
    """Hold the database-wide render lock: one render at a time across every process.

    Production runs two API workers, and the backfill script is a third process; ComfyUI is
    one GPU. Polls `pg_try_advisory_lock` (non-blocking) rather than the blocking
    `pg_advisory_lock` (F10 review): the blocking call would hold a pooled connection idle
    for as long as whoever else's render takes, and a pool only has so many connections to
    give out. A losing attempt's session is closed before the sleep, so nothing is held idle
    while waiting; holding one open through the render itself, once the lock is won, is
    accepted - that is the one connection actually doing something, for as long as one render
    takes, which is the entire point of serialising on it. Gives up after `COMFYUI_TIMEOUT`
    seconds of trying. Advisory locks are session-scoped, released by `pg_advisory_unlock` or
    by the database when the process holding it dies - so winning on one session and using a
    different one afterwards would not keep the lock; the same `db` is kept for both.
    """
    deadline = time.monotonic() + settings.COMFYUI_TIMEOUT
    while True:
        async with open_session() as db:
            got = (
                await db.execute(select(func.pg_try_advisory_lock(ICON_LOCK_KEY)))
            ).scalar()
            if got:
                try:
                    yield
                finally:
                    await db.execute(select(func.pg_advisory_unlock(ICON_LOCK_KEY)))
                    await db.commit()
                return
        if time.monotonic() >= deadline:
            raise comfyui.ComfyUITimeout(
                "Timed out waiting for the ComfyUI render lock"
            )
        await asyncio.sleep(LOCK_POLL_INTERVAL)


def _downscale(image_bytes: bytes) -> bytes:
    """ComfyUI's 1024x1024 output, downscaled to `settings.ICON_IMAGE_SIZE`.

    Kept as a transparent PNG - BiRefNet already removed the background in the graph itself
    (`icon_workflow.build_icon_workflow`); this only resizes.
    """
    with Image.open(io.BytesIO(image_bytes)) as original:
        image = original.convert("RGBA")
        size = settings.ICON_IMAGE_SIZE
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


async def draw_icon(product_id: UUID, hint: str | None = None) -> None:
    """Generate and store this product's icon. One at a time; never raises.

    Named `draw_icon` (not `generate_icon`) for Q18's drawer: `services/shelf_life_on_create.py`
    schedules it by this name, and that module and its tests are a sibling lane's, not this
    one's to rename.
    """
    try:
        async with _job_lock():
            await _generate(product_id, hint)
    except Exception as exc:  # noqa: BLE001 - a background job has nobody to raise to
        logger.warning(
            "Generating a product icon failed",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )


async def draw_icons(product_ids: Sequence[UUID], hint: str | None = None) -> None:
    """Generate these products' icons one after another.

    With `COMFYUI_BASE_URL` empty, refuses at once: one INFO line for the whole batch, no
    database read or write for any product in it.
    """
    if not settings.COMFYUI_BASE_URL:
        logger.info(
            "ComfyUI is disabled (COMFYUI_BASE_URL empty); no icon generation queued",
            extra={"count": len(product_ids)},
        )
        return
    for product_id in product_ids:
        await draw_icon(product_id, hint)


async def _generate(product_id: UUID, hint: str | None) -> None:
    async with open_session() as db:
        product = await crud_product.get_icon_subject(db, product_id)
        if product is None:
            return
        name = str(product.canonical_name)
        # Already `pending` means an explicit Regenerate got here first (`request_redraw`
        # marks it, with a fresh seed, before scheduling this job) - that is the cook asking
        # for exactly this image, so `cleared` (the cook un-clearing) does not second-guess
        # it. The automatic queue (rename, a new product) never pre-marks pending, so it
        # always sees something else here and `cleared` does apply. An exact/cook emoji is
        # never bypassed either way (F5) - see `_emoji_already_shown`.
        explicit = product.icon_status == IconStatus.PENDING
        if _emoji_already_shown(product):
            # Unreachable in practice - `request_redraw` already refuses this with 409
            # before ever marking pending - but if a pending row ever got here some other
            # way, it still must not hang "Generating..." forever.
            if explicit:
                await crud_product.mark_icon_failed(db, product)
                await _announce(product_id, name)
            return
        if not explicit and product.icon_status == IconStatus.CLEARED:
            return
        if await is_non_food(db, name):
            if explicit:
                # Never stuck "Generating..." forever: an explicit request this rule still
                # refuses answers at once, just unsuccessfully.
                await crud_product.mark_icon_failed(db, product)
                await _announce(product_id, name)
            return
        job_seed = (
            int(product.icon_seed)
            if explicit and product.icon_seed is not None
            else random.randint(0, RANDOM_SEED_MAX)
        )
        # Always persist the seed this job is about to use - including the explicit path,
        # where it is a same-value re-write: `_keep`'s seed check (F3) needs the row to
        # already carry whichever seed is current before the render starts, and a stale
        # `pending` the automatic queue just picked back up (its own job died without ever
        # recording one) would otherwise still have none to compare against.
        await crud_product.mark_icon_pending(db, product, job_seed)

    try:
        started = time.monotonic()
        workflow = build_icon_workflow(icon_subject(name, hint), seed=job_seed)
        async with _gateway_turn():
            outputs = await comfyui.render(workflow)
        if not outputs:
            raise comfyui.ComfyUIError("ComfyUI returned no image")
        image = _downscale(outputs[0])
        seconds = round(time.monotonic() - started, 1)
        # Storing it can fail too (a dropped connection, a constraint); that must still end
        # `failed`, not leave the row `pending` with nothing left to resolve it (review: the
        # original SVG drawer's `store_icon` call sat outside its own try for the same reason
        # this one no longer does).
        kept = await _keep(product_id, image, job_seed)
    except Exception as exc:  # noqa: BLE001 - anything here must still end `failed`
        logger.warning(
            "Generating a product icon broke; marking it failed",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )
        await _give_up(product_id)
        await _announce(product_id, name)
        return

    if not kept:
        return
    logger.info(
        "Product icon generated",
        extra={
            "product_id": str(product_id),
            "seconds": seconds,
            "seed": job_seed,
            "bytes": len(image),
        },
    )
    await _announce(product_id, name)


async def _keep(product_id: UUID, image: bytes, seed: int) -> bool:
    """Store the result unless nobody wants it any more. Whether anything was written.

    Re-reads the row under a lock (`FOR UPDATE`) and stores only if it is still `pending`
    *with this job's own seed* (F3 review): two Regenerates in flight each mark their own
    seed when they start, so whichever one is current when this runs is the one the cook
    asked for last - an older, slower job finishing after a newer one must not overwrite it,
    seed match or not just status.
    """
    async with open_session() as db:
        product = await crud_product.get_icon_subject(db, product_id, for_update=True)
        if (
            product is None
            or product.icon_status != IconStatus.PENDING
            or product.icon_seed != seed
        ):
            # Deleted, the cook chose the emoji while it was being generated, or a newer
            # Regenerate already took over this row: whichever one is current wins.
            logger.info(
                "Discarding a generated icon nobody wants any more",
                extra={"product_id": str(product_id)},
            )
            return False
        await crud_product.store_icon(db, product, image, seed)
    return True


async def _give_up(product_id: UUID) -> None:
    """Mark a broken job's row failed, keeping any earlier image. Never raises."""
    try:
        async with open_session() as db:
            product = await crud_product.get_icon_subject(db, product_id)
            if product is not None and product.icon_status == IconStatus.PENDING:
                await crud_product.mark_icon_failed(db, product)
    except Exception as exc:  # noqa: BLE001 - the stale-pending rule is the last resort
        logger.warning(
            "Could not mark a broken icon job failed; it will count as stale",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )


async def _announce(product_id: UUID, name: str) -> None:
    try:
        await broadcast_product_update(
            product_id, action="icon_updated", product_name=name
        )
    except Exception as exc:  # noqa: BLE001 - the icon is already stored
        logger.warning(
            "Could not broadcast a product icon",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )


# --- what the endpoints and the backfill call ------------------------------------------------


def schedule_icons(
    background_tasks: BackgroundTasks,
    product_ids: Sequence[UUID],
    hint: str | None = None,
) -> None:
    """Generate these products' icons once the response has been sent. None: nothing.

    Always queues `draw_icons` when there is at least one id - `draw_icons` is where
    `COMFYUI_BASE_URL` is actually checked (see its docstring for why the check is not here).
    """
    if not product_ids:
        return
    background_tasks.add_task(draw_icons, list(product_ids), hint)


class EmojiAlreadyShown(Exception):
    """Regenerate was asked for a product whose tile already shows an exact/cook emoji."""


async def request_redraw(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Mark the icon pending with a fresh seed, so the sheet says "Generating..." at once.

    This is Regenerate (Q18-G2, operator ask 2026-09-30): always a new random seed, and this
    mark is what tells the job that follows it is explicit - see `_generate`. Allowed on a
    `cleared` product (the cook's latest ask un-clears it); refused for one with an exact or
    cook emoji (F5, planner ruling) - that image could never show. None: no product.

    Raises:
        EmojiAlreadyShown: the product's emoji is `exact` or `cook`.
    """
    product = await crud_product.get_icon_subject(db, product_id)
    if product is None:
        return None
    if _emoji_already_shown(product):
        raise EmojiAlreadyShown(
            "This product shows an exact emoji; clear the emoji first"
        )
    await crud_product.mark_icon_pending(
        db, product, random.randint(0, RANDOM_SEED_MAX)
    )
    return product


async def clear_icon(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Drop the image: the tile shows the category emoji again. None: no product."""
    return await crud_product.clear_icon(db, product_id)


async def stored_icon(
    db: AsyncSession, product_id: UUID
) -> tuple[bytes, datetime] | None:
    """The stored image and when it last changed; None when there is none to show."""
    return await crud_product.stored_icon(db, product_id)


async def products_to_generate(
    db: AsyncSession, limit: int | None = None
) -> list[ProductMaster]:
    """Food products `icon_needs_generation` would pick, oldest first, capped at `limit`.

    The database query (`crud.products_needing_icons`) cannot check "is this food" itself
    (that needs `non_food_name`), so it is filtered here, after the SQL query, same as the
    per-product recheck in `still_needs_generation`.
    """
    candidates = await crud_product.products_needing_icons(db, stale_before())
    kept: list[ProductMaster] = []
    for product in candidates:
        if await is_non_food(db, str(product.canonical_name)):
            continue
        kept.append(product)
        if limit is not None and len(kept) >= limit:
            break
    return kept
