"""Exact Apple emoji or none, and the gap list (Q18 build).

The operator's rule (2026-09-27, `docs/spikes/Q18_exact_emoji.md`): a product tile shows an
Apple emoji only when one is exact - the closest match is never shown - decided per product,
never by family. Everything else keeps the category emoji until a generated image (a later,
separate ComfyUI lane) replaces it. Non-food gets nothing at all: no emoji, no proposal, no
generated icon ("I do not get why soap needs an emoji, it is not food.").

The build is table-first (the spike's own recommendation, after the model alone reached
precision ~0.97 but recall only ~0.70 against the operator's rulings):

1. `lookup()` checks the curated table (`app/resources/emoji_curated.json`, 109 exact + 58
   gap, seeded from the rulings) and the learned table (`product_emoji_learned`, confirmed
   proposals) - a hit needs no model call, ever.
2. A miss schedules a background proposal: the model answers `exact` / `borderline` / `none`
   for a batch of names, exactly as the spike's `scripts/emoji_trial.py` does, with the
   rulings as worked examples in place of the old family-level definition. `exact` is stored
   as `proposed` and shown nowhere until a person confirms it; `borderline` and `none` are
   stored as `none`. `confirm()` promotes it to `exact` and teaches the learned table, so the
   same generic name is never asked again - not even for a later product created under it.

Gateway rules (llama-swap requires a key since 2026-09-30) go through the shared
`services/llm_http.py`: a bearer `LLM_API_KEY`, a timeout of at least 300 s (a cold start
takes 2-5 minutes) with no retry on a timeout, and a `503` with `Retry-After` waited out and
retried within that budget. `scripts/emoji_trial.py` uses the same helper.
A model failure leaves the product unchanged; nothing here ever logs a full prompt at INFO.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.config import settings
from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.domain.product_names import normalize_product_name
from app.models.product_master import EmojiMatch, ProductMaster
from app.services.broadcast_helpers import broadcast_product_update
from app.services.llm_http import LLMAuthError
from app.services.llm_http import post_chat as llm_post_chat
from app.services.matching_service import normalize_receipt_name
from app.services.non_food import known_non_food

logger = get_logger(__name__)

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
REFERENCE_FILE = RESOURCES_DIR / "emoji_reference.json"
CURATED_FILE = RESOURCES_DIR / "emoji_curated.json"

# A cold start takes 2-5 minutes (the preamble); never below that, whatever LLM_TIMEOUT is.
MIN_PROPOSAL_TIMEOUT = 300.0


class EmojiProposalError(Exception):
    """The model could not be asked, or answered nothing usable."""


# --- the reference list and the curated table -------------------------------------------


def load_reference() -> list[dict[str, str]]:
    """Every emoji the picker, the proposal and the curated table may use."""
    data = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    return list(data["emoji"])


def reference_emoji() -> set[str]:
    return {entry["e"] for entry in load_reference()}


def _normalized(name: str) -> str:
    """The lookup key: NFC-normalized first, then `normalize_product_name`.

    A name typed or OCR'd on a different keyboard or OS can arrive NFD-decomposed (e.g.
    "e" + a combining grave accent instead of the precomposed "è"), which is a different
    string to `normalize_product_name` even though it is the same text. NFC-folding first
    means "Crème fraîche" matches the curated table's entry whichever form it comes in as.
    This stays local to this module rather than changing the shared
    `domain/product_names.py` key (PR #137 review).
    """
    return normalize_product_name(unicodedata.normalize("NFC", name or ""))


def _load_curated() -> tuple[dict[str, str | None], dict[str, str]]:
    """The curated table, keyed by `_normalized`, and its icon-brief hints."""
    data = json.loads(CURATED_FILE.read_text(encoding="utf-8"))
    table: dict[str, str | None] = {}
    hints: dict[str, str] = {}
    for row in data["products"]:
        key = _normalized(row["name"])
        table[key] = row.get("emoji")
        hint = row.get("hint")
        if hint:
            hints[key] = hint
    return table, hints


def gap_hint(generic_name: str) -> str | None:
    """The operator's own words for a gap product's future generated icon, if given."""
    _, hints = _load_curated()
    return hints.get(_normalized(generic_name))


def curated_lookup(generic_name: str) -> tuple[str | None, EmojiMatch] | None:
    """A curated-table hit: `(emoji, exact)`, or `(None, none)` for a gap row.

    None: the table does not know this generic name at all (not even as a gap row).
    """
    table, _ = _load_curated()
    key = _normalized(generic_name)
    if key not in table:
        return None
    emoji = table[key]
    return (emoji, EmojiMatch.EXACT) if emoji else (None, EmojiMatch.NONE)


async def lookup(
    db: AsyncSession, generic_name: str
) -> tuple[str | None, EmojiMatch] | None:
    """The curated table, then a confirmed proposal already learned. None: neither knows it.

    Case- and space-insensitive, and per product: there is no family matching anywhere here.
    """
    hit = curated_lookup(generic_name)
    if hit is not None:
        return hit
    learned = await crud_product.get_learned_emoji(db, _normalized(generic_name))
    return (learned, EmojiMatch.EXACT) if learned is not None else None


async def is_non_food(db: AsyncSession, generic_name: str) -> bool:
    """Whether the non-food vocabulary (Q1) already knows this generic name.

    Reuses `non_food_name`, keyed the same way a receipt line is: a generic name the cook
    has already called non-food on some receipt is not asked about again here either.
    """
    remembered = await known_non_food(db, None)
    return normalize_receipt_name(generic_name) in remembered


# --- applying a table hit, and the cook's own choice --------------------------------------


async def apply_on_create(db: AsyncSession, product: ProductMaster) -> bool:
    """Give a brand-new product its emoji from the table, right away. True: nothing more to
    do - either a hit was applied, or the row is already settled and must stay that way.

    This job is queued behind the shelf-life estimate, which can wait minutes on the model,
    so a product's `emoji_match` may already be `cook` or `cleared` by the time this runs -
    the cook's own choice, made in that window, and never overwritten by a table hit
    (PR #137 review). Non-food is skipped entirely - no emoji, no proposal. False means the
    caller should schedule a background proposal instead: the table does not know this name
    yet.
    """
    if product.emoji_match is not None:
        return True
    if await is_non_food(db, str(product.canonical_name)):
        return True
    hit = await lookup(db, str(product.canonical_name))
    if hit is None:
        return False
    emoji, match = hit
    await crud_product.set_emoji(db, product, emoji=emoji, match=match)
    return True


class NotProposed(Exception):
    """Confirm or reject was asked of a product whose emoji is not `proposed`."""


async def confirm(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """A `proposed` emoji becomes `exact`, and the generic name is learned. None: no product.

    Raises:
        NotProposed: the product's emoji is not `proposed`.
    """
    try:
        product = await crud_product.confirm_emoji_proposal(db, product_id)
    except crud_product.EmojiNotProposed as exc:
        raise NotProposed(str(exc)) from exc
    if product is not None and product.emoji:
        await crud_product.learn_emoji(
            db,
            _normalized(str(product.canonical_name)),
            str(product.emoji),
        )
    return product


async def reject(db: AsyncSession, product_id: UUID) -> ProductMaster | None:
    """A `proposed` emoji becomes `none`. None: no product.

    Raises:
        NotProposed: the product's emoji is not `proposed`.
    """
    try:
        return await crud_product.reject_emoji_proposal(db, product_id)
    except crud_product.EmojiNotProposed as exc:
        raise NotProposed(str(exc)) from exc


class UnknownEmoji(Exception):
    """The cook picked something outside the reference list."""


async def set_cook_choice(
    db: AsyncSession, product_id: UUID, emoji: str | None
) -> ProductMaster | None:
    """The cook's own pick (`cook`), or "no emoji" (`cleared`). None: no such product.

    Raises:
        UnknownEmoji: `emoji` is not one of the reference list's.
    """
    if emoji is not None and emoji not in reference_emoji():
        raise UnknownEmoji(f"{emoji!r} is not in the reference list")
    return await crud_product.set_cook_emoji(db, product_id, emoji)


# --- the model proposal --------------------------------------------------------------------

# The operator's own rulings, decided per product and never by family (spike doc, "Operator
# rulings"). In the model's prompt in place of the old family-level definition: the model at
# `low` reasoning otherwise carries that old definition and answers `borderline` for most of
# what the operator has since ruled exact.
RULING_EXAMPLES = """Worked examples, ruled by the operator - study how the SAME family splits:
- Gouda, Cheddar, Feta -> exact (a named cheese, whole or sliced, is its wedge emoji).
  Mozzarella, Blue cheese, Cottage cheese -> none (those do not look like a wedge as sold).
- Entrecôte, Pork chops -> exact (a named whole cut). Minced beef -> none (not a whole cut).
- Salmon, Rainbow trout, Baltic herring -> exact (a named fish, raw or processed).
  Canned tuna, Fish fingers -> none ("should look as they should": not a generic fish).
- Rice, Spaghetti, Instant noodles -> exact (a dish/shape can stand for its own ingredient).
  Canned tomatoes -> none (must not be a whole tomato emoji); Hot dog sausages -> none (must
  not be a hot-dog-with-bun emoji).
- Coffee, Tea, Red wine, Sparkling wine, Cola -> exact (a drink's own vessel or bottle counts).
- Orange -> exact (the closest NAMED citrus still counts when nothing more exact exists).
  Whole chicken -> none (a live bird, not the product); Margarine -> none; Chanterelles -> none
  (a specific mushroom, not the generic one).
A brand, a pack size, a variety or plural/singular never changes the food. The closest or a
similar-looking emoji is NEVER exact - when unsure, or only a broader/vessel/dish match
exists, answer borderline or none, never exact."""

PROPOSAL_PROMPT = """You decide which grocery products get a Unicode emoji as their icon.

The rule, binding: a product gets an emoji only when the emoji's official name (below) names
THE SAME FOOD as the product's generic name, at the level a cook means it, decided per product
and never by family.
- exact: precise enough that it needs no cognitive effort. Broccoli -> broccoli. Milk -> glass
  of milk.
- borderline: only a broader, vessel, or dish match exists, or you are unsure.
- none: nothing names this product. Never the closest or a similar-looking emoji.

{examples}

Emoji you may use, one per line as `emoji name` (use nothing else):
{emoji}

Products, numbered:
{products}

Answer with JSON only: {{"r": [{{"i": <number>, "e": "<emoji>" or null,
"m": "exact" | "borderline" | "none"}}, ...]}}, one row per product."""


def _build_prompt(names: Sequence[str], reference: list[dict[str, str]]) -> str:
    emoji = "\n".join(f"{e['e']} {e['name']}" for e in reference)
    products = "\n".join(f"{n}. {name}" for n, name in enumerate(names, start=1))
    return PROPOSAL_PROMPT.format(
        examples=RULING_EXAMPLES, emoji=emoji, products=products
    )


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "r": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "e": {"type": ["string", "null"]},
                    "m": {"type": "string", "enum": ["exact", "borderline", "none"]},
                },
                "required": ["i", "e", "m"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["r"],
    "additionalProperties": False,
}


def _build_payload(prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "product_emoji",
                "schema": RESPONSE_SCHEMA,
                "strict": True,
            },
        },
    }
    if settings.LLM_REASONING_STRENGTH:
        payload["chat_template_kwargs"] = {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }
    return payload


async def _post_proposal(payload: dict[str, Any]) -> str:
    """One chat completion, through the shared gateway helper (`services/llm_http.py`).

    Raises:
        EmojiProposalError: the gateway rejected `LLM_API_KEY`, the request failed or
            timed out, or the reply carried no usable message.
    """
    budget = max(settings.LLM_TIMEOUT, MIN_PROPOSAL_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=budget) as client:
            response = await llm_post_chat(client, payload, budget=budget)
    except LLMAuthError as exc:
        logger.warning("the LLM gateway rejected LLM_API_KEY")
        raise EmojiProposalError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise EmojiProposalError(repr(exc)) from exc
    try:
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise EmojiProposalError(repr(exc)) from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise EmojiProposalError("reply has no message content") from exc
    return str(content or "")


@dataclass(frozen=True)
class ProposalAnswer:
    """What the model said for one product, already checked against the reference list."""

    emoji: str | None
    match: EmojiMatch  # PROPOSED (exact) or NONE (borderline/none/invalid)


def _answer_object(content: str) -> dict[str, Any] | None:
    """The last JSON object with an `r` key; reasoning text before it may hold braces."""
    decoder = json.JSONDecoder()
    found = None
    for start in (i for i, ch in enumerate(content) if ch == "{"):
        try:
            value, _ = decoder.raw_decode(content, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("r"), list):
            found = value
    return found


def _parse_proposals(
    content: str, names: Sequence[str], reference: list[dict[str, str]]
) -> list[ProposalAnswer] | None:
    """One answer per name, in order. None: no usable JSON, or the numbering was not 1..n.

    Exactly as `scripts/emoji_trial.py` checks a batch: an emoji outside the reference list
    is dropped, a `none` that still names one drops it too (a closest match is never kept),
    and numbering that is not exactly 1..n makes the whole batch unusable, since rows are
    matched to products by number.
    """
    known = {e["e"] for e in reference}
    answer = _answer_object(content)
    if answer is None:
        return None
    raw_rows = answer["r"]
    indices = [row.get("i") if isinstance(row, dict) else None for row in raw_rows]
    expected = list(range(1, len(names) + 1))
    numbered = all(isinstance(i, int) and not isinstance(i, bool) for i in indices)
    if not numbered or sorted(indices) != expected:  # type: ignore[type-var]
        return None
    rows: dict[int, dict[str, Any]] = {row["i"]: row for row in raw_rows}

    results: list[ProposalAnswer] = []
    for number in range(1, len(names) + 1):
        row = rows[number]
        match = row.get("m")
        raw = row.get("e")
        if match == "exact" and isinstance(raw, str) and raw in known:
            results.append(ProposalAnswer(raw, EmojiMatch.PROPOSED))
        else:
            # borderline, none, or an exact with no usable emoji: never shown as a proposal.
            results.append(ProposalAnswer(None, EmojiMatch.NONE))
    return results


async def propose(
    names: Sequence[str], *, complete: Any = None
) -> list[ProposalAnswer] | None:
    """Ask the model about these generic names, one batch, one request. None: nothing usable.

    `complete` overrides how the request is sent, for tests; it defaults to the gateway call.
    """
    if not names:
        return []
    reference = load_reference()
    prompt = _build_prompt(names, reference)
    payload = _build_payload(prompt)
    post = complete or _post_proposal
    try:
        content = await post(payload)
    except EmojiProposalError as exc:
        logger.warning(
            "No usable emoji proposal from the model",
            extra={"count": len(names), "error": str(exc)},
        )
        return None
    parsed = _parse_proposals(content, names, reference)
    if parsed is None:
        logger.warning(
            "The model's emoji answer could not be trusted",
            extra={"count": len(names)},
        )
    return parsed


# --- scheduling the on-create hook (next to the icon drawing) -----------------------------


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    """A session of the job's own. Looked up at call time, so the tests can rebind it."""
    return app_session.AsyncSessionLocal()


def schedule_emoji(
    background_tasks: BackgroundTasks, product_ids: Sequence[UUID]
) -> None:
    """Give each new product its emoji, or propose one, once the response has been sent."""
    if product_ids:
        background_tasks.add_task(apply_emoji_for_new_products, list(product_ids))


async def apply_emoji_for_new_products(product_ids: Sequence[UUID]) -> None:
    """One product after another: a table hit applies at once, a miss asks the model.

    Never raises - a background job has nobody to raise to.
    """
    for product_id in product_ids:
        try:
            await _apply_one_on_create(product_id)
        except Exception as exc:  # noqa: BLE001 - see above
            logger.warning(
                "Applying a new product's emoji failed",
                extra={"product_id": str(product_id), "error": repr(exc)},
            )


async def _apply_one_on_create(product_id: UUID) -> None:
    async with open_session() as db:
        product = await crud_product.get_emoji_subject(db, product_id)
        if product is None:
            return
        name = str(product.canonical_name)
        hit = await apply_on_create(db, product)
    if hit:
        await _announce(product_id, name)
        return

    proposed = await propose([name])
    if not proposed:
        return
    (answer,) = proposed
    if answer.match != EmojiMatch.PROPOSED or answer.emoji is None:
        return
    async with open_session() as db:
        product = await crud_product.get_emoji_subject(db, product_id)
        if product is None or product.emoji_match is not None:
            # Gone, or already settled another way (the cook got there first).
            return
        await crud_product.set_emoji(
            db, product, emoji=answer.emoji, match=EmojiMatch.PROPOSED
        )
    await _announce(product_id, name)


async def _announce(product_id: UUID, name: str) -> None:
    try:
        await broadcast_product_update(
            product_id, action="icon_updated", product_name=name
        )
    except Exception as exc:  # noqa: BLE001 - the emoji is already stored
        logger.warning(
            "Could not broadcast a product's emoji",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )
