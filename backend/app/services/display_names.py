"""A product's name in the cook's chosen display language (Post-MVP frontier item 13).

Operator ruling (2026-10-02): "the system should have selectable display language. But of
course if the receipts are finnish the input data should kept as original." Products are
generic and English since MVP-R2 (`product_master.canonical_name`, `services/product_names.py`);
this module is Phase 1 of making that cook-facing rather than catalog-facing: an optional name
per language, stored in `product_display_name` (`models/product_display_name.py`) and read
through `ProductMaster.display_names`.

A display name is **not** a resolution key. `services/product_names.py` and `product_name` are
untouched here: a receipt line still resolves only through the canonical name and its learned
synonyms, in English, exactly as before. This module only ever reads the catalog to ask about a
name and writes `product_display_name` - never `product_name`, never matching.

A new product gets a Finnish name proposed by the model in the background, piggybacking on the
existing on-create estimate hook (`services/shelf_life_on_create.py`). `propose_finnish_names`
is called once for every new product `schedule_estimates` was given - a receipt confirm that
creates N products makes one request, not N (F3 review) - through the shared gateway helper
(`services/llm_http.py`): a bearer `LLM_API_KEY`, a timeout of at least 300 s (a cold start
takes 2-5 minutes) with no retry on a timeout, and a 503 with Retry-After waited out and
retried within that budget. A model failure, or one unusable row in an otherwise-good answer,
leaves that product with no display name and never drops any other product's - the frontend's
`displayName.ts` falls back to the canonical name - and nothing here ever logs a full prompt at
INFO.

A cook's own name (`source="cook"`, written by `PATCH /products/{id}`) is never overwritten by a
later proposal: the background job checks the cook has not set this language - before it ever
writes, and again right before it writes, since the cook may have gotten there while the model
was asked.

A rename re-proposes too (2026-10-03 production backfill finding): the model proposed from the
old English name, so a rename could leave a stale or wrong Finnish name in place
(`schedule_display_name_rename`, called from `PATCH /products/{id}`'s rename hook). It skips a
cook's own name exactly the same way; a missing or model-sourced name is re-asked, and the old
value (if any) stays shown until the new proposal lands - no flash of English.

Both the on-create and the rename proposal, plus the backfill script
(`scripts/backfill_display_names.py`), give the model up to three distinct printed receipt
names for the product (`printed_aliases`, from `store_product_alias`, newest first): the
printed text is the best evidence of the product's real Finnish wording, which the English
canonical name alone cannot carry (operator ruling, Finnish receipts "kept as original").
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, cast
from uuid import UUID

import httpx
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as app_session
from app.core.config import settings
from app.core.logging import get_logger
from app.crud import product_master as crud_product
from app.crud import store_product_alias as crud_alias
from app.models.product_master import ProductMaster
from app.services.broadcast_helpers import broadcast_product_update
from app.services.llm_http import LLMAuthError
from app.services.llm_http import post_chat as llm_post_chat

logger = get_logger(__name__)

# Phase 1 (this lane) ships Finnish only; Phase 2 is the app's own UI text, not this list.
# The code is written to allow more languages later - everything here is keyed on the code,
# nothing assumes there is exactly one.
SUPPORTED_LANGUAGES: list[str] = ["fi"]

# A cold start takes 2-5 minutes (the executor preamble); never below that, whatever
# LLM_TIMEOUT is - mirrors `services/product_emoji.py`'s MIN_PROPOSAL_TIMEOUT.
MIN_PROPOSAL_TIMEOUT = 300.0

# Up to this many distinct printed receipt names go in the prompt for one product
# (`printed_aliases`), newest first - enough to show the model the real wording without
# letting one heavily-bought product dominate the request.
MAX_PRINTED_ALIASES = 3


class DisplayNameProposalError(Exception):
    """The model could not be asked, or answered nothing usable."""


class UnsupportedLanguage(ValueError):
    """A language code that is not in SUPPORTED_LANGUAGES."""


def is_supported(language: str) -> bool:
    return language in SUPPORTED_LANGUAGES


# --- the model proposal ---------------------------------------------------------------------

PROPOSAL_PROMPT = """You translate grocery product names for a Finnish home cook's kitchen
inventory app. For each generic English product name below, give the natural Finnish word or
short phrase a Finnish cook would use for it on a shopping list or in the fridge - not a
literal dictionary translation, and not a brand name. Keep it short, in Finnish sentence case.
{receipt_rule}
Products, numbered:
{products}

Answer with JSON only: {{"r": [{{"i": <number>, "fi": "<name>"}}, ...]}}, one row per product,
in the same order they were given."""

RECEIPT_ALIAS_RULE = (
    "\nSome products also list the text a receipt printed for them. When one does, prefer "
    "the Finnish wording the receipt shows over a plain translation, tidied into a normal "
    'shopping-list name: normal case, no brand, no pack size, no "LUOMU", no percentages '
    '(for example "KAHVIKAURAJUOMA 1L" -> "Kahvikaurajuoma"; '
    '"TOFU KYLMÄSAVU LUOMU" -> "Kylmäsavutofu").\n'
)


def _build_prompt(
    names: Sequence[str], aliases: Sequence[Sequence[str]] | None = None
) -> str:
    alias_lists: Sequence[Sequence[str]] = (
        aliases if aliases is not None else [[] for _ in names]
    )
    lines = []
    for number, (name, product_aliases) in enumerate(
        zip(names, alias_lists, strict=True), start=1
    ):
        if product_aliases:
            printed = ", ".join(product_aliases)
            lines.append(f"{number}. {name} (printed on receipts: {printed})")
        else:
            lines.append(f"{number}. {name}")
    products = "\n".join(lines)
    receipt_rule = RECEIPT_ALIAS_RULE if any(alias_lists) else ""
    return PROPOSAL_PROMPT.format(products=products, receipt_rule=receipt_rule)


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "r": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "fi": {"type": "string"},
                },
                "required": ["i", "fi"],
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
                "name": "product_display_name",
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
        DisplayNameProposalError: the gateway rejected `LLM_API_KEY`, the request failed or
            timed out, or the reply carried no usable message.
    """
    budget = max(settings.LLM_TIMEOUT, MIN_PROPOSAL_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=budget) as client:
            response = await llm_post_chat(client, payload, budget=budget)
    except LLMAuthError as exc:
        logger.warning("the LLM gateway rejected LLM_API_KEY")
        raise DisplayNameProposalError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise DisplayNameProposalError(repr(exc)) from exc
    try:
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DisplayNameProposalError(repr(exc)) from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DisplayNameProposalError("reply has no message content") from exc
    return str(content or "")


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


def _parse_proposals(content: str, names: Sequence[str]) -> list[str | None] | None:
    """One Finnish name per name, in order. None: no usable JSON, or the numbering was not
    exactly 1..n - rows are matched to products by number, as `product_emoji._parse_proposals`
    does.
    """
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

    results: list[str | None] = []
    for number in range(1, len(names) + 1):
        raw = rows[number].get("fi")
        results.append(raw.strip() if isinstance(raw, str) and raw.strip() else None)
    return results


async def propose_finnish_names(
    names: Sequence[str],
    *,
    complete: Any = None,
    aliases: Sequence[Sequence[str]] | None = None,
) -> list[str | None] | None:
    """Ask the model for a Finnish name for each of these generic names, one batch, one
    request. None: nothing usable - the caller leaves every product without a proposal, the
    same as a model failure anywhere else in the catalog.

    `aliases`, one list per name in the same order, carries up to `MAX_PRINTED_ALIASES`
    printed receipt names per product (`printed_aliases`); omitted or empty, the prompt is
    exactly as it was before this carried any.

    `complete` overrides how the request is sent, for tests; it defaults to the gateway call.
    """
    if not names:
        return []
    prompt = _build_prompt(names, aliases)
    payload = _build_payload(prompt)
    post = complete or _post_proposal
    try:
        content = await post(payload)
    except DisplayNameProposalError as exc:
        logger.warning(
            "No usable display-name proposal from the model",
            extra={"count": len(names), "error": str(exc)},
        )
        return None
    parsed = _parse_proposals(content, names)
    if parsed is None:
        logger.warning(
            "The model's display-name answer could not be trusted",
            extra={"count": len(names)},
        )
    return parsed


# --- printed receipt aliases, the best evidence of the real Finnish wording -----------------


async def printed_aliases(db: AsyncSession, product_id: UUID) -> list[str]:
    """Up to `MAX_PRINTED_ALIASES` distinct printed receipt names for this product, newest
    first (`store_product_alias.last_seen`) - the best evidence of a product's real Finnish
    wording (operator ruling: Finnish receipts are "kept as original"). Read-only; never
    used as a resolution key, exactly as `display_names` itself never is.
    """
    rows = await crud_alias.aliases_for_product(db, product_id)
    ordered = sorted(rows, key=lambda row: row.last_seen, reverse=True)
    seen: set[str] = set()
    names: list[str] = []
    for row in ordered:
        name = str(row.receipt_name)
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) == MAX_PRINTED_ALIASES:
            break
    return names


# --- scheduling the on-create hook (next to the icon drawing and the emoji) -----------------


def open_session() -> AbstractAsyncContextManager[AsyncSession]:
    """A session of the job's own. Looked up at call time, so the tests can rebind it."""
    return app_session.AsyncSessionLocal()


def schedule_display_names(
    background_tasks: BackgroundTasks, product_ids: Sequence[UUID]
) -> None:
    """Propose a Finnish name for each of these new products, once the response has gone."""
    if product_ids:
        background_tasks.add_task(
            propose_display_names_for_new_products, list(product_ids)
        )


async def propose_display_names_for_new_products(product_ids: Sequence[UUID]) -> None:
    """One gateway call for every new product in this batch (F3 review): a receipt
    confirm that creates N products makes one request, not N. Never raises - a
    background job has nobody to raise to; a bad answer for one product, or a failure
    writing it, never drops any other product's in the same batch.
    """
    if not product_ids:
        return
    try:
        pending = await _pending_products(product_ids)
    except Exception as exc:  # noqa: BLE001 - see above
        logger.warning(
            "Could not read new products for a display-name proposal",
            extra={"product_ids": [str(p) for p in product_ids], "error": repr(exc)},
        )
        return
    if not pending:
        return

    # Phase 1 ships one language, and the model prompt only knows how to ask for
    # Finnish; a batch-of-languages request would only matter once SUPPORTED_LANGUAGES
    # grows (SUPPORTED_LANGUAGES itself still gates who counts as "pending" above).
    names = [name for _, name, _ in pending]
    aliases = [product_aliases for _, _, product_aliases in pending]
    proposed = await propose_finnish_names(names, aliases=aliases)
    if not proposed:
        return

    for (product_id, name, _), fi_name in zip(pending, proposed, strict=True):
        if not fi_name:
            continue  # this one row was unusable; every other product still gets its own
        await _store_one_proposal(product_id, name, fi_name)


async def _pending_products(
    product_ids: Sequence[UUID],
) -> list[tuple[UUID, str, list[str]]]:
    """Every product in this batch with no Finnish name yet: id, English name, and up to
    three printed receipt aliases (newest first) for the prompt.

    `populate_existing=True`, as `get_display_name_subject` also uses: a product just
    created earlier in the same request (and so already in this session's identity map,
    `display_name_rows` loaded then) could otherwise be read back here as it stood at
    that first load, missing a cook's name set to it since (PR #162 F3 review fix).
    """
    async with open_session() as db:
        products = (
            (
                await db.execute(
                    select(ProductMaster)
                    .where(ProductMaster.id.in_(product_ids))
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        pending = [
            (cast(UUID, product.id), str(product.canonical_name))
            for product in products
            if "fi" not in product.display_names
        ]
        return [
            (product_id, name, await printed_aliases(db, product_id))
            for product_id, name in pending
        ]


async def _store_one_proposal(product_id: UUID, name: str, fi_name: str) -> None:
    """Write one product's proposed name, if it is still wanted. Never raises - this
    product's own failure must not stop the rest of the batch (F3 review).

    Only a cook's own name (`source="cook"`) blocks this: a rename re-proposal is meant
    to overwrite an existing `model` row, not merely fill a gap (`schedule_display_name_
    rename`).
    """
    try:
        async with open_session() as db:
            product = await crud_product.get_display_name_subject(db, product_id)
            if product is None or product.display_name_sources.get("fi") == "cook":
                # Gone, or the cook (or an earlier run) already set this language.
                return
            await crud_product.set_display_name(
                db, product, language="fi", name=fi_name, source="model"
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - see module docstring
        logger.warning(
            "Storing a product's proposed display name failed",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )
        return
    await _announce(product_id, name)


async def _propose_one_on_create(product_id: UUID) -> None:
    """One product on its own - the batched path (above) with a single-element batch."""
    await propose_display_names_for_new_products([product_id])


# --- scheduling a rename's re-proposal (2026-10-03 production backfill finding) -------------


def schedule_display_name_rename(
    background_tasks: BackgroundTasks, product_id: UUID
) -> None:
    """A rename re-proposes the product's Finnish name, once the response has gone.

    The model proposed from the old English name, so a rename can leave a stale or
    outright wrong Finnish name behind. Scheduled unconditionally from the rename hook,
    exactly as the icon redraw already is (F2 review) - `_propose_one_on_rename` is
    where the cook's-own-name check happens, not here.
    """
    background_tasks.add_task(_propose_one_on_rename, product_id)


async def _propose_one_on_rename(product_id: UUID) -> None:
    """Re-propose this product's Finnish name after a rename, unless the cook set it.

    A missing name is proposed too (the product may have had none to begin with, or an
    earlier proposal failed) - this is "the same as create" for whichever language rows
    are not the cook's own. The stale value, if any, is left in place until the new
    proposal lands: nothing here ever clears a name it cannot yet replace.
    """
    try:
        async with open_session() as db:
            product = await crud_product.get_display_name_subject(db, product_id)
            if product is None or product.display_name_sources.get("fi") == "cook":
                return
            name = str(product.canonical_name)
            aliases = await printed_aliases(db, product_id)
    except Exception as exc:  # noqa: BLE001 - a background job has nobody to raise to
        logger.warning(
            "Could not read a product for a rename's display-name re-proposal",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )
        return

    proposed = await propose_finnish_names([name], aliases=[aliases])
    if not proposed or not proposed[0]:
        return
    await _store_one_proposal(product_id, name, proposed[0])


async def _announce(product_id: UUID, name: str) -> None:
    try:
        await broadcast_product_update(product_id, action="updated", product_name=name)
    except Exception as exc:  # noqa: BLE001 - the name is already stored
        logger.warning(
            "Could not broadcast a product's display name",
            extra={"product_id": str(product_id), "error": repr(exc)},
        )
