"""Product icons the local model draws (Q18).

Every tile used to show its category's emoji, so every fruit was an apple. The Q18 spike
(docs/spikes/Q18_product_icons.md) had the model draw a flat 48x48 SVG per product in one fixed
style, and it drew 19 of 20 products usably, each one distinct. The operator ruled on
2026-09-26: the local model draws every product's icon, the markup is stored in the database,
and the category emoji is always the fallback.

What the model answers is untrusted markup. `sanitise()` parses it with an entity-safe parser
and keeps only a small allowlist of shapes and attributes, each value checked against a strict
grammar, so the stored SVG holds geometry and hex colours and nothing else. The iPad only ever
shows it through `<img src>`, which runs no script even if something slipped through, and
`GET /products/{id}/icon.svg` serves it under a `default-src 'none'` policy on top.

Drawing takes seconds to minutes, so it runs as a background job after the response has gone:
`draw_icon()` opens its own session, never raises, and runs one drawing at a time in the
process, because the gateway serves one request at a time. A failure keeps the previous drawing
(or the emoji) and says `failed`; nothing in the receipt or stock path waits for an icon.
"""

import asyncio
import re
import time
import weakref
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.config import settings
from app.core.logging import get_logger
from app.models.product_master import IconStatus, ProductMaster
from app.services.broadcast_helpers import broadcast_product_update

logger = get_logger(__name__)

ATTEMPTS = 2
MAX_SVG_BYTES = 8192  # the spike's drawings were 239-547 bytes
MAX_ANSWER_BYTES = 65536  # an answer this long is not a 40 px icon; do not parse it
VIEWBOX = "0 0 48 48"
SVG_NS = "http://www.w3.org/2000/svg"

PALETTE = {
    "outline": "#2B2B2B",
    "red": "#E4453A",
    "orange": "#F29B38",
    "yellow": "#F5D547",
    "green": "#5BA84A",
    "brown": "#9A6334",
    "cream": "#F3E6C8",
    "white": "#FFFFFF",
}

DRAW_PROMPT = """Draw a flat icon of this grocery product as SVG: {name} (category: {category}).
{hint}
Rules, all of them binding:
- One <svg> element with xmlns="http://www.w3.org/2000/svg" and viewBox="0 0 48 48".
- Use only these colours, as hex: {palette}.
- Either a 2 px outline in #2B2B2B (stroke-width="2") on every shape, or no outline at all.
- Only <g>, <path>, <circle>, <ellipse>, <rect>, <polygon>, <polyline> and <line>.
- No text, no gradients, no filters, no <image>, <script>, <style> or <foreignObject>, no
  event attributes, no links or external references.
- Simple and recognisable at 40 px: a few bold shapes, like a modern emoji. Draw the product
  itself as it looks in a shop (its package if it is sold in one), not a scene.

Answer with the SVG only, no explanation and no code fence."""

HINT_LINE = "What it looks like, in the cook's words: {hint}\n"


class IconRejected(ValueError):
    """The answer holds no drawing worth keeping."""


class IconModelError(Exception):
    """The gateway could not be reached, or answered without a message."""


# --- the sanitiser ---------------------------------------------------------------------------

SHAPES = {"path", "circle", "ellipse", "rect", "polygon", "polyline", "line"}
CONTAINERS = {"g"}

_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER = re.compile(rf"^{_NUMBER}$")
NUMBER_LIST = re.compile(rf"^{_NUMBER}(?:(?:\s*,\s*|\s+){_NUMBER})*$")
# Path data: commands and numbers only. No letter outside the command set gets through.
PATH_DATA = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9eE.,+\-\s]+$")
POINTS = re.compile(r"^[0-9eE.,+\-\s]+$")
# A hex colour or `none`. url(#...), currentColor and names are dropped, so a fill cannot
# point at a gradient or an external resource.
COLOUR = re.compile(r"^(#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|none)$")
TRANSFORM_STEP = re.compile(
    rf"\s*(translate|scale|rotate|matrix)\s*\(\s*({_NUMBER}(?:(?:\s*,\s*|\s+){_NUMBER})*)\s*\)\s*,?"
)
TRANSFORM_ARITY = {
    "translate": {1, 2},
    "scale": {1, 2},
    "rotate": {1, 3},
    "matrix": {6},
}

NUMERIC_ATTRIBUTES = {
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "width",
    "height",
    "stroke-width",
    "stroke-miterlimit",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
}
ENUM_ATTRIBUTES = {
    "fill-rule": {"nonzero", "evenodd"},
    "clip-rule": {"nonzero", "evenodd"},
    "stroke-linecap": {"butt", "round", "square"},
    "stroke-linejoin": {"miter", "round", "bevel"},
}


def _transform_ok(value: str) -> bool:
    position = 0
    steps = 0
    while position < len(value):
        match = TRANSFORM_STEP.match(value, position)
        if match is None:
            return value[position:].strip() == "" and steps > 0
        arguments = re.split(r"\s*,\s*|\s+", match.group(2).strip())
        if len(arguments) not in TRANSFORM_ARITY[match.group(1)]:
            return False
        position = match.end()
        steps += 1
    return steps > 0


def _value_ok(name: str, value: str) -> bool:
    """Whether `value` is a well-formed value for the allowlisted attribute `name`."""
    if name in NUMERIC_ATTRIBUTES:
        return bool(NUMBER.match(value))
    if name in ("fill", "stroke"):
        return bool(COLOUR.match(value))
    if name in ENUM_ATTRIBUTES:
        return value in ENUM_ATTRIBUTES[name]
    if name == "d":
        return bool(PATH_DATA.match(value))
    if name == "points":
        return bool(POINTS.match(value))
    if name == "stroke-dasharray":
        return value == "none" or bool(NUMBER_LIST.match(value))
    if name == "transform":
        return _transform_ok(value)
    return False


def _svg_name(tag: str) -> str | None:
    """The local name of an element in the SVG namespace (or none); None for any other."""
    if tag.startswith("{"):
        namespace, _, name = tag[1:].partition("}")
        return name if namespace == SVG_NS else None
    return tag


def sanitise(svg_text: str) -> tuple[str, bool]:
    """Keep only the allowlist of the model's SVG. Returns (clean SVG, whether it changed).

    Disallowed elements are dropped with their whole subtree, and so is an element in any
    namespace but SVG's, whatever its local name. Attributes off the list, namespaced ones,
    and values that do not match their grammar are dropped from the elements that stay. Text
    is dropped. The viewBox is forced to 48x48.

    Raises:
        IconRejected: not well-formed XML, a DTD or entity, no `<svg>` root, nothing drawable
            left, or a result over MAX_SVG_BYTES.
    """
    if len(svg_text.encode()) > MAX_ANSWER_BYTES:
        raise IconRejected("answer too long to be an icon")
    try:
        root = fromstring(svg_text, forbid_dtd=True)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise IconRejected(
            f"not an acceptable XML document: {type(exc).__name__}"
        ) from exc
    if _svg_name(root.tag) != "svg":
        raise IconRejected("the root element is not <svg>")

    changed = False

    def clean(element: ET.Element, out: ET.Element) -> int:
        """Copy what is allowed of `element` into `out`; returns the shapes kept below."""
        nonlocal changed
        for name, value in element.attrib.items():
            if out.tag == "svg" and name == "viewBox":
                continue
            value = value.strip()
            if name.startswith("{") or not _value_ok(name, value):
                changed = True
                continue
            out.set(name, value)
        if (element.text or "").strip():
            changed = True
        shapes = 0
        for child in element:
            if (child.tail or "").strip():
                changed = True
            local = _svg_name(child.tag)
            if local is not None and (local in SHAPES or local in CONTAINERS):
                kept = ET.SubElement(out, local)
                below = clean(child, kept)
                if local in CONTAINERS and below == 0:
                    out.remove(kept)  # an empty group draws nothing
                    changed = True
                    continue
                shapes += 1 if local in SHAPES else below
            else:
                changed = True
        return shapes

    cleaned = ET.Element("svg")
    cleaned.set("viewBox", VIEWBOX)
    if root.get("viewBox", "").strip() != VIEWBOX:
        changed = True
    if clean(root, cleaned) == 0:
        raise IconRejected("nothing drawable left after sanitising")
    cleaned.set("xmlns", SVG_NS)
    markup = ET.tostring(cleaned, encoding="unicode")
    if len(markup.encode()) > MAX_SVG_BYTES:
        raise IconRejected(f"the drawing is over {MAX_SVG_BYTES} bytes")
    return markup, changed


def extract_svg(text: str) -> str | None:
    """The first `<svg>...</svg>` in the answer; reasoning or a code fence around it is fine."""
    match = re.search(r"<svg\b.*?</svg>", text, re.DOTALL | re.IGNORECASE)
    return match.group(0) if match else None


# --- the model -------------------------------------------------------------------------------


def build_prompt(name: str, category: str, hint: str | None = None) -> str:
    palette = ", ".join(f"{colour} {code}" for colour, code in PALETTE.items())
    hint_line = HINT_LINE.format(hint=hint.strip()) if hint and hint.strip() else ""
    return DRAW_PROMPT.format(
        name=name, category=category, palette=palette, hint=hint_line
    )


async def _complete(prompt: str) -> str:
    payload: dict[str, Any] = {
        "model": settings.ICON_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": 0.2,
    }
    # Muse Glimmer's template takes a reasoning strength; other models' templates do not.
    if "muse-glimmer" in settings.ICON_MODEL and settings.LLM_REASONING_STRENGTH:
        payload["chat_template_kwargs"] = {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }
    try:
        async with httpx.AsyncClient(timeout=settings.ICON_TIMEOUT) as client:
            response = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise IconModelError(f"Icon request failed: {exc!r}") from exc
    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise IconModelError("Icon response has no message content") from exc
    return str(content)


async def _attempt(prompt: str) -> tuple[str | None, list[str]]:
    """Up to ATTEMPTS drawings; returns (clean SVG or None, why each failed attempt failed)."""
    reasons: list[str] = []
    for _ in range(ATTEMPTS):
        try:
            text = await _complete(prompt)
        except Exception as exc:  # noqa: BLE001 - one bad attempt must not end the job
            reasons.append(f"model: {type(exc).__name__}")
            continue
        raw = extract_svg(text)
        if raw is None:
            reasons.append("no <svg> in the answer")
            continue
        try:
            clean, _ = sanitise(raw)
        except IconRejected as exc:
            reasons.append(str(exc))
            continue
        return clean, reasons
    return None, reasons


# --- the job ---------------------------------------------------------------------------------


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    """A session of the job's own. Looked up at call time, so the tests can rebind it."""
    return app_session.AsyncSessionLocal()


# One lock per event loop; the app runs one, so this is process-wide there. Keyed by loop so
# a lock never outlives the loop it was bound to (each test has its own).
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _job_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


async def draw_icon(product_id: UUID, hint: str | None = None) -> None:
    """Draw and store this product's icon. One at a time; never raises."""
    try:
        async with _job_lock():
            await _draw(product_id, hint)
    except Exception as exc:  # noqa: BLE001 - a background job has nobody to raise to
        logger.warning(
            "Drawing a product icon failed",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )


async def draw_icons(product_ids: Sequence[UUID], hint: str | None = None) -> None:
    """Draw these products' icons one after another."""
    for product_id in product_ids:
        await draw_icon(product_id, hint)


def schedule_icons(
    background_tasks: BackgroundTasks,
    product_ids: Sequence[UUID],
    hint: str | None = None,
) -> None:
    """Draw these products' icons once the response has been sent. None: nothing."""
    if product_ids:
        background_tasks.add_task(draw_icons, list(product_ids), hint)


async def _draw(product_id: UUID, hint: str | None) -> None:
    async with open_session() as db:
        product = await db.get(ProductMaster, product_id)
        if product is None or product.icon_status == IconStatus.CLEARED:
            return
        name, category = str(product.canonical_name), str(product.category)
        if product.icon_status != IconStatus.PENDING:
            product.icon_status = IconStatus.PENDING  # type: ignore[assignment]
            await db.commit()

    started = time.monotonic()
    svg, reasons = await _attempt(build_prompt(name, category, hint))
    seconds = round(time.monotonic() - started, 1)

    async with open_session() as db:
        product = await db.get(ProductMaster, product_id, populate_existing=True)
        if product is None or product.icon_status != IconStatus.PENDING:
            # Deleted, or the cook chose the emoji while it was being drawn: theirs wins.
            logger.info(
                "Discarding a product icon nobody wants any more",
                extra={"product_id": str(product_id)},
            )
            return
        if svg is None:
            product.icon_status = IconStatus.FAILED  # type: ignore[assignment]
        else:
            product.icon_svg = svg
            product.icon_status = IconStatus.READY  # type: ignore[assignment]
            product.icon_updated_at = datetime.now(UTC)  # type: ignore[assignment]
        await db.commit()

    if svg is None:
        logger.warning(
            "No usable icon from the model; keeping what the tile had",
            extra={
                "product_id": str(product_id),
                "model": settings.ICON_MODEL,
                "seconds": seconds,
                "reasons": reasons,
            },
        )
    else:
        logger.info(
            "Product icon drawn",
            extra={
                "product_id": str(product_id),
                "model": settings.ICON_MODEL,
                "seconds": seconds,
                "attempts": len(reasons) + 1,
                "bytes": len(svg),
            },
        )
    try:
        await broadcast_product_update(
            product_id, action="icon_updated", product_name=name
        )
    except Exception as exc:  # noqa: BLE001 - the icon is already stored
        logger.warning(
            "Could not broadcast a product icon",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )


# --- what the endpoints call -----------------------------------------------------------------


async def request_redraw(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Mark the icon pending, so the editor says "Drawing..." at once. None: no product."""
    product = await db.get(ProductMaster, product_id)
    if product is None:
        return None
    product.icon_status = IconStatus.PENDING  # type: ignore[assignment]
    await db.commit()
    return product


async def clear_icon(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """Drop the drawing: the tile shows the category emoji again. None: no product."""
    product = await db.get(ProductMaster, product_id)
    if product is None:
        return None
    product.icon_svg = None
    product.icon_status = IconStatus.CLEARED  # type: ignore[assignment]
    product.icon_updated_at = None  # type: ignore[assignment]
    await db.commit()
    return product


async def stored_icon(
    db: AsyncSession, product_id: UUID
) -> tuple[str, datetime] | None:
    """The stored drawing and when it last changed; None when there is none to show."""
    row = (
        await db.execute(
            select(ProductMaster.icon_svg, ProductMaster.icon_updated_at).where(
                ProductMaster.id == product_id,
                ProductMaster.icon_svg.is_not(None),
                ProductMaster.icon_updated_at.is_not(None),
            )
        )
    ).first()
    if row is None:
        return None
    return str(row[0]), row[1]
