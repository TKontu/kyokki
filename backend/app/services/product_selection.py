"""Asking the model to pick a product from a shortlist we offered.

The one place a non-deterministic judgement is allowed to touch identity, and it is
constrained twice: the model only ever sees a handful of candidates per line, and its
answer is rejected unless it is one of the candidates that line was offered
(`docs/PRODUCT_RESOLUTION_SPEC.md` §3.3).

One request per receipt, for the lines that deterministic keys could not resolve. A
receipt with nothing unresolved - a warm catalog - makes no call at all.
"""

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm_extractor import LLMExtractionError, extract_json_object
from app.services.llm_http import LLMAuthError, post_chat
from app.services.product_names import normalize_product_name

logger = get_logger(__name__)

# The last four rules below (raw ingredient vs. manufactured product, one animal's cut
# vs. another's, a processing form vs. a named kind, a broad catalog word vs. a
# catch-all) were added from the Q37 live runs on c2.muse-glimmer against the reported
# pairs (reported_pairs.json): before them, the model confirmed butter as "Spread",
# turkey cold cuts as "Ham" and pesto as "Dip" - the exact wrong snaps Q37 reports. With
# them, 3 consecutive runs of the 15 reported-pair cases (6 pre-Q37 H53 cases, 9 Q37
# ones) passed 12, 13 and 12 of 15; the pre-Q37 cases always pass, and butter/Spread,
# baking chocolate/Chips, cashew nuts/Dip and chicken mince/Chicken fillet remain
# flaky - a real limit of this model at LLM_REASONING_STRENGTH=low, not a wiring gap
# (see PR #143). This prompt is used only for the lines deterministic keys could not
# resolve, never for the main extraction read, so it does not touch the fixtures'
# completeness or category counts (K-Citymarket 15/15, S-kaupat 49/49, REWE DE
# synthetic 6/6, all measured unchanged against base in the same PR).
INSTRUCTIONS = """For each line, pick the catalog product that is the same thing, or null if none is.

Same thing means a home cook would put them on one shopping-list line.
What a cook buys and uses differently is a DIFFERENT product - plant milk vs dairy
milk, a different cut, a smaller or processed form:
- "Oat milk" is not "Milk". "Sour cream" is not "Cream". "Peanut butter" is not "Butter".
- "Cherry tomato" is not "Tomato". "Pineapple" is not "Apple".
A named kind of the same food, bought and used the same way, is the SAME product:
"Granny Smith" is "Apple", "Clementine" is "Mandarin". A processing form - ground,
minced, sliced, whole - is not a named kind: a milled grain is still a different,
processed form of the crop it is milled from, the same as any other different or
processed form above - "Flour" is not "Wheat".
Sharing a word does not make two products the same: "Tortilla chips" is not "Tortilla",
"Lemonade" is not "Lemon", "Chocolate milk" is not "Chocolate".
A raw ingredient is not a manufactured product made from it, however near they sit on a
shelf: "Cucumber" is not "Pickle". "Milk" is not "Cheese".
Meat from one animal is not the same product as a cut or cold cut from another, even
when a shopper would reach for either from the same fridge case: "Duck" is not
"Goose". "Lamb" is not "Beef".
A broad word for a whole aisle or kind of food is not a match for one specific thing
that could plausibly be filed there: it has to be the SAME product, not merely a
plausible shelf for it.
The candidates are only the nearest names in the catalog, not a list that contains the
answer. If none of them is the same thing, answer null: null is a good answer, and a
wrong pick is worse than none.
Only pick a product whose id appears in that line's candidates.
When you answer null, you may also give "g": the generic English shopping-list name the
line actually is - singular, no brand, the same rule the line's own "g" follows. Give it
only when the candidates' names are wrong for this line, not when you are simply
declining to confirm a right one.

Example. Lines:
[{"id": "a", "n": "ARLA LAKTOOSITON MAITO", "g": "Lactose-free milk", "c": "dairy",
  "candidates": [{"p": "p1", "name": "Lactose-free milk"}, {"p": "p2", "name": "Milk"}]},
 {"id": "b", "n": "HARTWALL LIMONADI", "g": "Lemonade", "c": "beverages",
  "candidates": [{"p": "p3", "name": "Orange juice"}, {"p": "p4", "name": "Lemon"}]}]
Answer: {"r": [{"id": "a", "p": "p1"}, {"id": "b", "p": null}]}

Answer with JSON only: {"r": [{"id": "<line id>", "p": "<product id>" or null,
"g": "<optional corrected generic name, only when p is null>"}]}

Lines:
"""


@dataclass(frozen=True)
class SelectionLine:
    """One unresolved line and the products it may be matched against."""

    line_id: str
    printed: str
    generic: str | None
    category: str | None
    candidate_ids: tuple[str, ...]
    candidate_names: tuple[str, ...]


def build_prompt(lines: list[SelectionLine]) -> str:
    payload = [
        {
            "id": line.line_id,
            "n": line.printed,
            "g": line.generic,
            "c": line.category,
            "candidates": [
                {"p": pid, "name": name}
                for pid, name in zip(
                    line.candidate_ids, line.candidate_names, strict=True
                )
            ],
        }
        for line in lines
    ]
    import json

    return INSTRUCTIONS + json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True)
class SelectionAnswer:
    """What `parse_selection` read out of one response: picks, plus corrections.

    ``corrected`` is only ever populated for a line whose answer was ``null`` (Q37b):
    a pick needs no corrected name, it already is one of the offered candidates.
    """

    products: dict[str, UUID]
    corrected: dict[str, str]


class SelectionResult(dict[str, UUID]):
    """Line id -> chosen product, same shape `select_products` always returned.

    A plain ``dict`` subclass, so any caller or test double that only reads this as
    ``dict[str, UUID]`` (as every caller before Q37b did) keeps working unchanged; the
    corrected generic names Q37b adds ride along on ``.corrected`` for the one caller
    that reads it (`ProductResolution._select`).
    """

    def __init__(
        self, products: dict[str, UUID], corrected: dict[str, str] | None = None
    ) -> None:
        super().__init__(products)
        self.corrected: dict[str, str] = dict(corrected or {})


def parse_selection(content: str, lines: list[SelectionLine]) -> SelectionAnswer:
    """Line id -> chosen product, keeping only answers we actually offered.

    A model that invents a product id, repeats one from another line, or answers for a
    line that was not asked about is ignored rather than trusted. A corrected generic
    name (Q37b) is kept only for a line whose pick was null, and only when it is not
    merely the name of a candidate that line was offered and the model just rejected -
    repeating a rejected name back is not a correction.
    """
    offered = {
        line.line_id: dict(zip(line.candidate_ids, line.candidate_names, strict=True))
        for line in lines
    }
    data = extract_json_object(content)
    answers = data.get("r") if isinstance(data, dict) else None
    if not isinstance(answers, list):
        raise LLMExtractionError("Selection response has no 'r' list")

    chosen: dict[str, UUID] = {}
    corrected: dict[str, str] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        line_id = answer.get("id")
        if line_id is None:
            continue
        line_id = str(line_id)
        candidates = offered.get(line_id)
        if candidates is None:
            continue

        product_id = answer.get("p")
        if product_id is not None:
            product_id = str(product_id)
            if product_id not in candidates:
                logger.warning(
                    "Ignoring a selection that was never offered",
                    extra={"line_id": line_id, "product_id": product_id},
                )
                continue
            try:
                chosen[line_id] = UUID(product_id)
            except ValueError:
                logger.warning(
                    "Ignoring an unparseable product id", extra={"line_id": line_id}
                )
            continue

        corrected_name = answer.get("g")
        if not isinstance(corrected_name, str):
            continue
        tidy = " ".join(corrected_name.split())
        if not tidy:
            continue
        rejected_names = {normalize_product_name(name) for name in candidates.values()}
        if normalize_product_name(tidy) in rejected_names:
            continue
        corrected[line_id] = tidy
    return SelectionAnswer(products=chosen, corrected=corrected)


async def select_products(lines: list[SelectionLine]) -> SelectionResult:
    """One request for the whole receipt. Returns line id -> product.

    Raises:
        LLMExtractionError: the gateway could not be reached or the answer was unusable.
            The caller leaves those lines unresolved rather than guessing.
    """
    if not lines:
        return SelectionResult({})

    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": build_prompt(lines)}],
        "max_tokens": settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE,
    }
    if settings.LLM_REASONING_STRENGTH:
        payload["chat_template_kwargs"] = {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.LLM_ESTIMATE_TIMEOUT) as client:
            response = await post_chat(
                client, payload, budget=settings.LLM_ESTIMATE_TIMEOUT
            )
            response.raise_for_status()
            body = response.json()
    except LLMAuthError as exc:
        raise LLMExtractionError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise LLMExtractionError(f"Selection request failed: {exc!r}") from exc

    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMExtractionError("Selection response has no message content") from exc

    answer = parse_selection(content, lines)
    logger.info(
        "Products selected",
        extra={
            "model": settings.LLM_MODEL,
            "asked": len(lines),
            "answered": len(answer.products),
            "corrected": len(answer.corrected),
            "seconds": round(time.monotonic() - started, 1),
        },
    )
    return SelectionResult(answer.products, answer.corrected)
