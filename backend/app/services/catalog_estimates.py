"""Asking the model how long the products in the catalog keep.

Q7 fixed why the model stopped estimating shelf lives during extraction, and Q11 gave a
stored figure the provenance that lets a later estimate replace a placeholder. Neither
repairs what is already there: on the homelab 46 of 50 products carried their category's
blanket figure, and the receipts that created them are `confirmed`, which is terminal.
For 45 of them no estimate was ever made at all.

So this asks directly, about product names rather than receipt lines. That is a
departure from the 2026-09-17 ruling that the knowledge comes from the model *at
extraction time*, and the operator took it deliberately on 2026-09-19: it is still the
model rather than the seed list the ruling was written against.

**A separate prompt and a separate module, on purpose.** Twice this month a change to
`_INSTRUCTIONS` destroyed estimates it was not aimed at - the known-products clause took
shelf lives from 39 to 4 of 49 (Q7), and a `pk` field took them from 39 to 26 to 4 (Q8),
both silently. Nothing here can reach the receipt path, and that claim is checked by
re-running the 49-line fixture unchanged.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.crud.product_master import MovedInventoryItem, get_products
from app.services.expiry_recompute import recompute_expiry_for_product
from app.services.llm_extractor import LLMExtractionError, extract_json_object

logger = get_logger(__name__)

# How many products go in one request. Names are short, so this is nothing like a
# receipt read; the cap exists so one large catalog cannot build an unbounded prompt.
BATCH_SIZE = 25

# What a shelf life may plausibly be, in days, by the kind of thing it is. The model is
# asked for a number and sometimes answers with a confident wrong one; a band is cheaper
# than trusting it, and this writes to the whole catalog at once. Anything outside its
# category's band is dropped rather than clamped - a rejected answer leaves the
# placeholder in place, which is where it already was.
PLAUSIBLE_DAYS: dict[str, tuple[int, int]] = {
    "meat": (1, 60),
    "fish": (1, 30),
    "dairy": (2, 120),
    "cheese": (5, 365),
    "produce": (2, 120),
    "fruits": (2, 120),
    "bread": (2, 800),
    "frozen": (30, 730),
    "pantry": (7, 1825),
    "beverages": (7, 1825),
    "condiments": (7, 1825),
    "snacks": (7, 730),
}
# A category nobody listed above still gets a sanity check, just a loose one.
DEFAULT_BAND = (1, 1825)

INSTRUCTIONS = """For each product, say how long it keeps unopened, and how long once opened.

These are generic kitchen staples, not specific brands. Answer for the ordinary version
a home cook would buy in Finland, stored the usual way for its kind.

- d = days it keeps unopened, from the day it was bought. A whole number.
- o = days it keeps once opened, or null when opening does not apply (an apple, an onion).
  o is always smaller than d.

Examples: minced beef -> d 2; fresh chicken -> d 3; sliced ham -> d 10, o 5;
salami -> d 30, o 14; hard cheese -> d 60, o 21; milk -> d 7, o 5; rye crispbread ->
d 720, o 60; dried pasta -> d 720; onion -> d 30; banana -> d 7.

Answer with JSON only: {"r": [{"id": "<the id given>", "d": <days>, "o": <days or null>}]}

Products:
"""


@dataclass(frozen=True)
class EstimateRequest:
    """One product to ask about. `id` is echoed back so answers cannot drift."""

    id: str
    name: str
    category: str


@dataclass(frozen=True)
class Estimate:
    """What the model said about one product, after validation."""

    id: str
    shelf_life_days: int
    opened_shelf_life_days: int | None


def build_prompt(products: list[EstimateRequest]) -> str:
    payload = [{"id": p.id, "n": p.name, "c": p.category} for p in products]
    return INSTRUCTIONS + json.dumps(payload, ensure_ascii=False)


def _plausible(days: int, category: str) -> bool:
    low, high = PLAUSIBLE_DAYS.get(category, DEFAULT_BAND)
    return low <= days <= high


def _whole(value: Any) -> int | None:
    """A positive whole number of days, or None. Accepts 30.0, rejects 0 and "soon"."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return days if days > 0 else None


def parse_estimates(content: str, asked: list[EstimateRequest]) -> list[Estimate]:
    """Keep only answers for products we asked about, with a plausible number.

    The discipline `parse_selection` applies to identity, applied to a number: an answer
    about a product that was not in this batch is discarded, and so is one whose shelf
    life is outside what its category could possibly mean. A dropped answer is not a
    failure - the product keeps the placeholder it already had.
    """
    by_id = {p.id: p for p in asked}
    data = extract_json_object(content)
    rows = data.get("r")
    if not isinstance(rows, list):
        raise LLMExtractionError("Estimate response has no result list")

    estimates: list[Estimate] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        product_id = str(row.get("id") or "")
        product = by_id.get(product_id)
        if product is None or product_id in seen:
            logger.warning(
                "Ignoring an estimate we did not ask for",
                extra={"product_id": product_id},
            )
            continue

        days = _whole(row.get("d"))
        if days is None or not _plausible(days, product.category):
            logger.warning(
                "Ignoring an implausible shelf life",
                extra={
                    "product": product.name,
                    "category": product.category,
                    "answered": row.get("d"),
                },
            )
            continue

        opened = _whole(row.get("o"))
        # Opening something can only shorten its life. A model that says otherwise has
        # not understood the question for that line; drop the part it got wrong.
        if opened is not None and opened >= days:
            opened = None

        seen.add(product_id)
        estimates.append(
            Estimate(id=product_id, shelf_life_days=days, opened_shelf_life_days=opened)
        )
    return estimates


async def _complete(batch: list[EstimateRequest]) -> str:
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": build_prompt(batch)}],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
    }
    if settings.LLM_REASONING_STRENGTH:
        payload["chat_template_kwargs"] = {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }

    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            response = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise LLMExtractionError(f"Estimate request failed: {exc!r}") from exc

    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMExtractionError("Estimate response has no message content") from exc
    return str(content)


async def estimate_shelf_lives(products: list[EstimateRequest]) -> list[Estimate]:
    """Ask about every product, in batches. Returns only the answers worth keeping.

    Raises:
        LLMExtractionError: the gateway could not be reached, or a batch came back
            unusable. Nothing is written by this function either way; the caller decides.
    """
    if not products:
        return []

    started = time.monotonic()
    estimates: list[Estimate] = []
    for index in range(0, len(products), BATCH_SIZE):
        batch = products[index : index + BATCH_SIZE]
        estimates.extend(parse_estimates(await _complete(batch), batch))

    logger.info(
        "Catalog shelf lives estimated",
        extra={
            "model": settings.LLM_MODEL,
            "asked": len(products),
            "answered": len(estimates),
            "seconds": round(time.monotonic() - started, 1),
        },
    )
    return estimates


@dataclass(frozen=True)
class ProposedChange:
    """One product the model would change, and what it would change it to."""

    id: UUID
    canonical_name: str
    category: str
    current_days: int
    proposed_days: int
    current_opened: int | None
    proposed_opened: int | None


@dataclass(frozen=True)
class CatalogRefresh:
    """What a refresh found, and whether any of it was written."""

    considered: int
    answered: int
    changes: list[ProposedChange]
    applied: bool
    # The stock whose expiry moved with the shelf lives, for the caller to broadcast (Q12).
    moved: list[MovedInventoryItem] = field(default_factory=list)


async def refresh_catalog_shelf_lives(
    db: AsyncSession, *, apply: bool = False
) -> CatalogRefresh:
    """Re-estimate the shelf lives nobody ever chose, and optionally keep them.

    Only products whose `shelf_life_source` is `category` are candidates: those carry
    the blanket figure creation had to invent, which is a placeholder rather than an
    answer (Q11). A product the model estimated is left alone, and one the cook set is
    never even sent - their names are the only thing the model is told, so a correction
    cannot be argued with by a batch job.

    `apply` defaults to False everywhere it is reachable. This walks the whole catalog
    at once, and a write that size should be something somebody looked at first.
    """
    candidates = [
        product
        for product in await get_products(db)
        if str(product.shelf_life_source) == "category"
    ]
    if not candidates:
        return CatalogRefresh(considered=0, answered=0, changes=[], applied=False)

    by_id = {str(product.id): product for product in candidates}
    estimates = await estimate_shelf_lives(
        [
            EstimateRequest(
                id=str(product.id),
                name=str(product.canonical_name),
                category=str(product.category),
            )
            for product in candidates
        ]
    )

    changes: list[ProposedChange] = []
    for estimate in estimates:
        product = by_id[estimate.id]
        current_days = int(product.default_shelf_life_days)
        current_opened = (
            int(product.opened_shelf_life_days)
            if product.opened_shelf_life_days is not None
            else None
        )
        # An opened shelf life is filled only when it is missing, the way `_fill_gaps`
        # has always treated it: NULL already means "unknown", so nothing is being
        # overruled, and a cook who set one did so in the same editor.
        proposed_opened = (
            estimate.opened_shelf_life_days
            if current_opened is None
            else current_opened
        )
        if (
            estimate.shelf_life_days == current_days
            and proposed_opened == current_opened
        ):
            continue
        changes.append(
            ProposedChange(
                id=UUID(estimate.id),
                canonical_name=str(product.canonical_name),
                category=str(product.category),
                current_days=current_days,
                proposed_days=estimate.shelf_life_days,
                current_opened=current_opened,
                proposed_opened=proposed_opened,
            )
        )

    moved: list[MovedInventoryItem] = []
    if apply:
        for change in changes:
            product = by_id[str(change.id)]
            product.default_shelf_life_days = change.proposed_days
            product.shelf_life_source = "model"
            product.opened_shelf_life_days = change.proposed_opened
            # The stock dated by the old figure moves with it, in the same transaction so a
            # refresh is still all-or-nothing (Q12).
            moved.extend(await recompute_expiry_for_product(db, product))
        await db.commit()

    logger.info(
        "Catalog shelf lives refreshed",
        extra={
            "considered": len(candidates),
            "answered": len(estimates),
            "changes": len(changes),
            "applied": apply,
            "items_redated": len(moved),
        },
    )
    return CatalogRefresh(
        considered=len(candidates),
        answered=len(estimates),
        changes=changes,
        applied=apply,
        moved=moved,
    )
