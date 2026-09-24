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

logger = get_logger(__name__)

INSTRUCTIONS = """For each line, pick the catalog product that is the same thing, or null if none is.

Same thing means a home cook would put them on one shopping-list line.
Different variety, plant milk vs dairy milk, or a different cut are DIFFERENT products:
- "Oat milk" is not "Milk". "Sour cream" is not "Cream". "Peanut butter" is not "Butter".
- "Cherry tomato" is not "Tomato". "Pineapple" is not "Apple".
Sharing a word does not make two products the same: "Tortilla chips" is not "Tortilla",
"Lemonade" is not "Lemon", "Chocolate milk" is not "Chocolate".
The candidates are only the nearest names in the catalog, not a list that contains the
answer. If none of them is the same thing, answer null: null is a good answer, and a
wrong pick is worse than none.
Only pick a product whose id appears in that line's candidates.

Example. Lines:
[{"id": "a", "n": "ARLA LAKTOOSITON MAITO", "g": "Lactose-free milk", "c": "dairy",
  "candidates": [{"p": "p1", "name": "Lactose-free milk"}, {"p": "p2", "name": "Milk"}]},
 {"id": "b", "n": "HARTWALL LIMONADI", "g": "Lemonade", "c": "beverages",
  "candidates": [{"p": "p3", "name": "Orange juice"}, {"p": "p4", "name": "Lemon"}]}]
Answer: {"r": [{"id": "a", "p": "p1"}, {"id": "b", "p": null}]}

Answer with JSON only: {"r": [{"id": "<line id>", "p": "<product id>" or null}]}

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


def parse_selection(content: str, lines: list[SelectionLine]) -> dict[str, UUID]:
    """Line id -> chosen product, keeping only answers we actually offered.

    A model that invents a product id, repeats one from another line, or answers for a
    line that was not asked about is ignored rather than trusted.
    """
    offered = {line.line_id: set(line.candidate_ids) for line in lines}
    data = extract_json_object(content)
    answers = data.get("r") if isinstance(data, dict) else None
    if not isinstance(answers, list):
        raise LLMExtractionError("Selection response has no 'r' list")

    chosen: dict[str, UUID] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        line_id, product_id = answer.get("id"), answer.get("p")
        if product_id is None or line_id is None:
            continue
        line_id, product_id = str(line_id), str(product_id)
        if product_id not in offered.get(line_id, set()):
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
    return chosen


async def select_products(lines: list[SelectionLine]) -> dict[str, UUID]:
    """One request for the whole receipt. Returns line id -> product.

    Raises:
        LLMExtractionError: the gateway could not be reached or the answer was unusable.
            The caller leaves those lines unresolved rather than guessing.
    """
    if not lines:
        return {}

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
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            response = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise LLMExtractionError(f"Selection request failed: {exc!r}") from exc

    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMExtractionError("Selection response has no message content") from exc

    chosen = parse_selection(content, lines)
    logger.info(
        "Products selected",
        extra={
            "model": settings.LLM_MODEL,
            "asked": len(lines),
            "answered": len(chosen),
            "seconds": round(time.monotonic() - started, 1),
        },
    )
    return chosen
