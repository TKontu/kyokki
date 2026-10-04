"""Propose visual subjects for gap products (Q18 subjects): see docs/spikes/q18_subjects/.

Generated icons draw the *word*, not the food - SDXL reads "Fish fingers" as a whole fish
and "Karelian pasty" as a pie wedge (`docs/spikes/Q18_icon_styles.md`,
`docs/spikes/q18_g2_live/README.md`). A short *visual* description instead - shape, colour,
packaging, how it is served, no brand, one object, centred - fixes most of it. This script
asks the LLM gateway (slot ``c2.muse-glimmer``, the one request-at-a-time rule everywhere
else in this codebase follows) for that description, once per product, so
``app.services.icon_subjects`` never calls it at render time.

No product list is hardcoded here beyond skipping the operator's own briefs
(`app.services.icon_briefs`), which always win anyway - every name this script asks about
comes from ``--names`` or ``--names-file``, given by whoever runs it.

Two steps, on purpose, so a bad subject never reaches a render queue unseen:

    python -m scripts.propose_icon_subjects --names-file gap_products.txt --dry-run
    python -m scripts.propose_icon_subjects --names-file gap_products.txt --out draft.json
    # the operator reads draft.json and edits or removes any entry that reads wrong
    python -m scripts.propose_icon_subjects --apply draft.json

``--dry-run`` only prints what the model proposes; nothing is written anywhere. A plain run
(no ``--dry-run``, no ``--apply``) writes the *draft* named by ``--out`` - never the cache
itself - for the operator to review. ``--apply`` is the only way anything reaches the live
cache (``app/resources/icon_subjects.json`` by default): it merges the reviewed draft into
whatever is already cached, keyed by the same normalized name
``app.services.icon_subjects`` looks up with, and never touches a product's operator brief.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.product_names import normalize_product_name
from app.services.icon_briefs import brief_for
from app.services.llm_extractor import LLMExtractionError, extract_json_object
from app.services.llm_http import LLMAuthError, post_chat

logger = get_logger(__name__)

# Names are short, so one request easily carries many; capped so one run cannot build an
# unbounded prompt the way `catalog_estimates.BATCH_SIZE` caps its own batches.
BATCH_SIZE = 20

DEFAULT_CACHE_PATH = Path("app/resources/icon_subjects.json")
DEFAULT_DRAFT_PATH = Path("icon_subjects.draft.json")

INSTRUCTIONS = """For each grocery product, describe only what it looks like to a camera: a short
phrase an image generator can draw instead of the product's own name.

Rules:
- Shape, colour, packaging, and how it is usually served or arranged - as sold or served in
  Finland. No brand.
- Exactly one object, centred - never a scene, a meal, or more than one item.
- Never use the product's own name or a word that reads as something else (a product name
  that sounds like a place, an animal, or an unrelated object must not appear in the
  description - "Karelian pasty" is a pastry, not a place; "Cottage cheese" is curds, not a
  building).
- About 6-12 words, plain and concrete, like a photo caption.

Examples:
"Fish fingers" -> "breaded rectangular fish sticks, golden crumb, three on a plate"
"Karelian pasty" -> "oval rye pastry, scalloped crimped edge, rice filling showing"
"Quark" -> "a tub of smooth white soft cheese with a spoon in it"
"Hot dog sausages" -> "a row of plump pink sausages in a vacuum pack"

Answer with JSON only: {"r": [{"id": "<the id given>", "subject": "<visual description>"}]}

Products:
"""


@dataclass(frozen=True)
class SubjectRequest:
    """One product to ask about. `id` is echoed back so answers cannot drift (H51-style)."""

    id: str
    name: str


def build_prompt(batch: list[SubjectRequest]) -> str:
    payload = [{"id": r.id, "n": r.name} for r in batch]
    return INSTRUCTIONS + json.dumps(payload, ensure_ascii=False)


def _clean_subject(value: Any, name: str) -> str | None:
    """A usable visual description, or None. Rejects a blank answer and one that is
    really just the product's own name restated (the whole point is to stop drawing the
    word) - a real visual description almost always has to use some of the same words
    too ("sour cream" looks like sour cream), so only a near-bare restatement is
    rejected, not every description that happens to share a word with the name."""
    if not isinstance(value, str):
        return None
    text = value.strip().strip(".")
    if not text:
        return None
    normalized_text = normalize_product_name(text)
    normalized_name = normalize_product_name(name)
    if normalized_text == normalized_name:
        return None
    if len(normalized_text.split()) <= len(normalized_name.split()) + 1:
        return None
    return text


def parse_subjects(content: str, asked: list[SubjectRequest]) -> dict[str, str]:
    """Product name -> visual subject, for every answer worth keeping."""
    by_id = {r.id: r.name for r in asked}
    data = extract_json_object(content)
    rows = data.get("r")
    if not isinstance(rows, list):
        raise LLMExtractionError("Subject response has no result list")

    subjects: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        request_id = str(row.get("id") or "")
        name = by_id.get(request_id)
        if name is None:
            logger.warning(
                "Ignoring a subject we did not ask for", extra={"id": request_id}
            )
            continue
        subject = _clean_subject(row.get("subject"), name)
        if subject is None:
            logger.warning(
                "Ignoring an unusable proposed subject",
                extra={"product": name, "answered": row.get("subject")},
            )
            continue
        subjects[name] = subject
    return subjects


async def _complete(batch: list[SubjectRequest]) -> str:
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
            response = await post_chat(client, payload, budget=settings.LLM_TIMEOUT)
            response.raise_for_status()
            body = response.json()
    except LLMAuthError as exc:
        raise LLMExtractionError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise LLMExtractionError(f"Subject request failed: {exc!r}") from exc

    try:
        content = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMExtractionError("Subject response has no message content") from exc
    return str(content)


async def propose_subjects(names: list[str]) -> dict[str, str]:
    """Ask the gateway about every name, in batches. Returns only usable answers.

    Raises:
        LLMExtractionError: the gateway could not be reached, or a batch came back
            unusable. Nothing is written by this function either way.
    """
    if not names:
        return {}

    started = time.monotonic()
    requests = [SubjectRequest(id=str(i), name=name) for i, name in enumerate(names, 1)]
    subjects: dict[str, str] = {}
    for index in range(0, len(requests), BATCH_SIZE):
        batch = requests[index : index + BATCH_SIZE]
        subjects.update(parse_subjects(await _complete(batch), batch))

    logger.info(
        "Icon subjects proposed",
        extra={
            "model": settings.LLM_MODEL,
            "asked": len(names),
            "answered": len(subjects),
            "seconds": round(time.monotonic() - started, 1),
        },
    )
    return subjects


# --- names in, cache out -------------------------------------------------------------------


def _collect_names(names: list[str], names_file: Path | None) -> list[str]:
    """Every distinct name from ``--names`` and ``--names-file``, in order given."""
    all_names = list(names)
    if names_file is not None:
        for line in names_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                all_names.append(stripped)

    seen: set[str] = set()
    unique: list[str] = []
    for name in all_names:
        key = normalize_product_name(name)
        if key not in seen:
            seen.add(key)
            unique.append(name)
    return unique


def _skip_briefed(names: list[str]) -> list[str]:
    """Drop any product the operator already described - its brief always wins anyway."""
    kept = [name for name in names if brief_for(name) is None]
    skipped = len(names) - len(kept)
    if skipped:
        print(f"skipping {skipped} product(s) that already have an operator brief")
    return kept


def _apply(draft_path: Path, cache_path: Path) -> int:
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        print(f"{draft_path} is not a JSON object; refusing to apply it")
        return 1
    cache: dict[str, Any] = {}
    if cache_path.exists():
        existing = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            cache = existing
    cache.update(draft)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"merged {len(draft)} entr{'y' if len(draft) == 1 else 'ies'} into {cache_path}"
        f" ({len(cache)} total)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0] if __doc__ else ""
    )
    parser.add_argument(
        "--names", nargs="*", default=[], help="product names to ask about"
    )
    parser.add_argument(
        "--names-file", type=Path, help="a file with one product name per line"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print proposals, write nothing"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_DRAFT_PATH,
        help="where to write the draft for the operator to review (never the cache itself)",
    )
    parser.add_argument(
        "--apply",
        type=Path,
        help="merge this reviewed draft file into the cache, instead of asking the gateway",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="the cache file app.services.icon_subjects reads",
    )
    args = parser.parse_args(argv)

    if args.apply is not None:
        return _apply(args.apply, args.cache)

    names = _skip_briefed(_collect_names(args.names, args.names_file))
    if not names:
        print(
            "nothing to propose (no names given, or all already have an operator brief)"
        )
        return 0

    try:
        proposed = asyncio.run(propose_subjects(names))
    except LLMExtractionError as exc:
        print(f"could not propose subjects: {exc}")
        return 1

    missing = [name for name in names if name not in proposed]
    if args.dry_run:
        for name in names:
            print(f"{name}: {proposed.get(name, '(no usable answer)')}")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(proposed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            f"wrote {len(proposed)} proposed subject(s) to {args.out} for operator review"
        )
    if missing:
        print(f"{len(missing)} product(s) got no usable answer: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
