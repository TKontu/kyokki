"""Q18 exact-emoji trial: which products have an exact Unicode emoji, and which need an icon.

The operator's rule (2026-09-27): a product shows an Apple emoji only when one names exactly
that food - its CLDR short name names the same thing a cook means by the product's generic
name. The closest match is never used; everything without an exact emoji goes on the gap
list, to get a generated emoji-style image later. This script asks the model, in batches, for
each product's exact emoji (or none) from the reference list in `scripts/emoji_food.json`,
checks every answer against that list, and writes a Markdown table plus CSV and JSON.

This is a spike tool, not part of the app: it changes nothing in the database.

    python -m scripts.emoji_trial --names names.csv --out /tmp/emoji.md
    python -m scripts.emoji_trial --from-db --out /tmp/emoji.md
    python -m scripts.emoji_trial --build-reference emoji-test.txt

`--names` reads `name,category` CSV or one bare name per line (a `name` header row is
skipped, repeated names are reported and skipped).
`--from-db` reads `product_master.canonical_name` and `category` in a read-only transaction
(`--limit N` for a trial on part of the catalog).
`--build-reference` regenerates the reference JSON from Unicode's `emoji-test.txt`.
Requests go one at a time to `LLM_BASE_URL` with `LLM_MODEL` and `LLM_API_KEY` (override the
first two with --url/--model), each with `LLM_TIMEOUT` (--timeout). The output files are
rewritten after every batch, so an interrupted run keeps the batches it finished. A batch
whose answer numbering is not exactly 1..n is rejected as `invalid`.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

REFERENCE_FILE = Path(__file__).resolve().parent / "emoji_food.json"
# iPad 8th gen runs iPadOS 17/18. Emoji 15.1 arrived in iPadOS 17.4 and 16.0 only in 18.4,
# so 15.1 is the newest version every supported iPad renders once it is up to date.
DEFAULT_CUTOFF = "15.1"
MATCHES = ("exact", "borderline", "none")
OUTCOMES = (*MATCHES, "invalid", "missing")
VARIATION_SELECTOR = "\ufe0f"

# The whole Food & Drink group, the plant subgroups, and the household goods a grocery
# receipt carries (by CLDR name, from any other group).
FOOD_GROUPS = {"Food & Drink"}
PLANT_SUBGROUPS = {"plant-flower", "plant-other"}
EXTRA_NAMES = {
    # animals sold as food (Emoji 18.0 files the seafood under animal-marine)
    "fish",
    "octopus",
    "crab",
    "lobster",
    "shrimp",
    "squid",
    "oyster",
    "chicken",
    # household
    "soap",
    "roll of paper",
    "sponge",
    "toothbrush",
    "lotion bottle",
    "broom",
    "basket",
    "bucket",
    "razor",
    "bubbles",
    "safety pin",
    "wastebasket",
    "shopping bags",
    "candle",
    "light bulb",
    "battery",
    "pill",
    "adhesive bandage",
    "thermometer",
    "syringe",
}


@dataclass(frozen=True)
class Product:
    name: str
    category: str | None


@dataclass(frozen=True)
class Result:
    name: str
    category: str | None
    emoji: str | None
    match: str  # exact | borderline | none | invalid | missing
    why: str


class GatewayError(Exception):
    """The model request failed or answered with nothing usable."""


# --- the reference list ------------------------------------------------------------------


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


_LINE = re.compile(
    r"^(?P<codes>[0-9A-F ]+?)\s*;\s*(?P<status>[\w-]+)\s*#\s*(?P<emoji>\S+)"
    r"\s+E(?P<version>\d+\.\d+)\s+(?P<name>.+)$"
)


def build_reference(emoji_test: str, cutoff: str = DEFAULT_CUTOFF) -> dict[str, Any]:
    """The grocery-relevant emoji from Unicode's `emoji-test.txt`, fully qualified forms only."""
    version = ""
    group = subgroup = ""
    kept: list[dict[str, str]] = []
    newer: list[dict[str, str]] = []
    for line in emoji_test.splitlines():
        if line.startswith("# Version:"):
            version = line.split(":", 1)[1].strip()
        elif line.startswith("# group:"):
            group = line.split(":", 1)[1].strip()
        elif line.startswith("# subgroup:"):
            subgroup = line.split(":", 1)[1].strip()
        match = _LINE.match(line)
        if not match or match["status"] != "fully-qualified":
            continue
        name = match["name"].strip()
        wanted = (
            group in FOOD_GROUPS or subgroup in PLANT_SUBGROUPS or name in EXTRA_NAMES
        )
        if not wanted:
            continue
        entry = {
            "e": match["emoji"],
            "name": name,
            "version": match["version"],
            "group": group,
            "subgroup": subgroup,
        }
        if version_key(entry["version"]) > version_key(cutoff):
            newer.append(entry)
        else:
            kept.append(entry)
    return {
        "source": "https://unicode.org/Public/emoji/latest/emoji-test.txt",
        "unicode_emoji_version": version,
        "cutoff": cutoff,
        "cutoff_reason": (
            "iPad 8th gen runs iPadOS 17/18; Emoji 15.1 needs iPadOS 17.4, "
            "Emoji 16.0 needs iPadOS 18.4"
        ),
        "emoji": kept,
        "excluded_newer": newer,
    }


def load_reference_file(path: Path = REFERENCE_FILE) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def write_reference(data: dict[str, Any], path: Path = REFERENCE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ",\n".join(
        "    " + json.dumps(e, ensure_ascii=False) for e in data["emoji"]
    )
    newer = ",\n".join(
        "    " + json.dumps(e, ensure_ascii=False) for e in data["excluded_newer"]
    )
    head = {k: v for k, v in data.items() if k not in ("emoji", "excluded_newer")}
    body = json.dumps(head, ensure_ascii=False, indent=2)[:-2]
    path.write_text(
        f'{body},\n  "emoji": [\n{lines}\n  ],\n  "excluded_newer": [\n{newer}\n  ]\n}}\n',
        encoding="utf-8",
    )


# --- the product names -------------------------------------------------------------------


def _dedupe(products: list[Product]) -> list[Product]:
    """Drop repeated names (case-insensitive), keeping the first, and say which went."""
    seen: set[str] = set()
    unique = []
    dropped = []
    for product in products:
        key = product.name.strip().lower()
        if not key:
            continue
        if key in seen:
            dropped.append(product)
            continue
        seen.add(key)
        unique.append(product)
    for product in dropped:
        print(
            f"  duplicate name skipped: {product.name}"
            + (f" ({product.category})" if product.category else "")
        )
    return unique


def read_names(path: Path) -> list[Product]:
    products = []
    with path.open(encoding="utf-8", newline="") as handle:
        for number, row in enumerate(csv.reader(handle)):
            if not row or not row[0].strip():
                continue
            name = row[0].strip()
            category = row[1].strip() if len(row) > 1 and row[1].strip() else None
            # A header row: `name` alone or `name,category`.
            if number == 0 and name.lower() == "name":
                continue
            products.append(Product(name, category))
    return _dedupe(products)


SessionFactory = Callable[[], AbstractAsyncContextManager[Any]]


async def load_from_db(
    sessions: SessionFactory, limit: int | None = None
) -> list[Product]:
    """Every catalog product's name and category, read in a read-only transaction."""
    query = (
        "SELECT canonical_name, category FROM product_master "
        "ORDER BY lower(canonical_name)"
    )
    async with sessions() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        if limit is None:
            result = await db.execute(text(query))
        else:
            result = await db.execute(text(query + " LIMIT :limit"), {"limit": limit})
        rows = result.all()
    return _dedupe([Product(str(name), category) for name, category in rows])


def _default_sessions() -> AbstractAsyncContextManager[Any]:
    import app.db.session as app_session

    return app_session.AsyncSessionLocal()


async def _dispose_engine() -> None:
    """Close the app engine's pool inside the loop, so exit prints no loop-closed noise."""
    import app.db.session as app_session

    await app_session.engine.dispose()


async def _read_catalog(limit: int | None) -> list[Product]:
    try:
        return await load_from_db(_default_sessions, limit=limit)
    finally:
        await _dispose_engine()


# --- the model ---------------------------------------------------------------------------

PROMPT = """You decide which products in a kitchen inventory get a Unicode emoji as their icon.

The rule, binding: a product gets an emoji only when the emoji's official name (below) names
THE SAME FOOD OR THING as the product's generic name, at the level a cook means it.
- exact: the emoji's name is this product. Broccoli -> 🥦 broccoli. Grapes -> 🍇 grapes.
  Eggs -> 🥚 egg. Cookies -> 🍪 cookie. Milk -> 🥛 glass of milk. Ice cream -> 🍨 ice cream.
  A brand, a pack size, a variety or plural/singular does not change the food: "Granny Smith
  apple" is still an apple, "Cherry tomatoes" are still tomatoes.
- borderline: the emoji's name is a broader or overlapping term, and a cook could argue
  either way. Entrecôte -> 🥩 cut of meat (generic meat). Rye bread -> 🍞 bread (the emoji is a
  white loaf). Give the emoji and say what the doubt is; the operator decides.
- none: no emoji names this product. NEVER use the closest or a similar-looking emoji.
  Parsnip -> none (🥕 is carrot). Quark -> none. Sauerkraut -> none. Hummus -> none.
  Answer e = null for none.

Emoji you may use, one per line as `emoji name` (use nothing else):
{emoji}

Products, numbered, with their category:
{products}

Answer with JSON only: {{"r": [{{"i": <number>, "e": "<emoji>" or null,
"m": "exact" | "borderline" | "none", "why": "<a few words>"}}, ...]}}, one row per product."""


def build_prompt(batch: list[Product], reference: list[dict[str, Any]]) -> str:
    emoji = "\n".join(f"{e['e']} {e['name']}" for e in reference)
    products = "\n".join(
        f"{n}. {p.name}" + (f" (category: {p.category})" if p.category else "")
        for n, p in enumerate(batch, start=1)
    )
    return PROMPT.format(emoji=emoji, products=products)


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
                    "m": {"type": "string", "enum": list(MATCHES)},
                    "why": {"type": "string"},
                },
                "required": ["i", "e", "m", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["r"],
    "additionalProperties": False,
}


def build_payload(
    prompt: str, model: str, reasoning: str | None, max_tokens: int
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "emoji_trial",
                "schema": RESPONSE_SCHEMA,
                "strict": True,
            },
        },
    }
    if reasoning:
        payload["chat_template_kwargs"] = {"reasoning_strength": reasoning}
    return payload


def _message_content(body: Any) -> str:
    """The first choice's message content, or GatewayError for any other shape."""
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise GatewayError(f"reply has no choices: {str(body)[:200]}")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise GatewayError(f"reply has no message: {str(choices[0])[:200]}")
    return str(message.get("content") or "")


def post_chat(
    payload: dict[str, Any],
    *,
    url: str,
    api_key: str,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """One chat completion. Raises GatewayError on any failure."""
    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0), transport=transport
        ) as client:
            response = client.post(
                f"{url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GatewayError(repr(exc)) from exc
    return _message_content(body)


# --- the answers -------------------------------------------------------------------------


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


def parse_answers(
    content: str, batch: list[Product], reference: list[dict[str, Any]]
) -> list[Result]:
    """One Result per product in `batch`, in order. Answers are checked, never trusted."""
    known = {e["e"].replace(VARIATION_SELECTOR, ""): e["e"] for e in reference}
    answer = _answer_object(content)
    if answer is None:
        return [
            Result(p.name, p.category, None, "missing", "no JSON answer") for p in batch
        ]
    raw_rows = answer["r"]
    indices = [row.get("i") if isinstance(row, dict) else None for row in raw_rows]
    expected = list(range(1, len(batch) + 1))
    numbered = all(isinstance(i, int) and not isinstance(i, bool) for i in indices)
    if not numbered or sorted(indices) != expected:  # type: ignore[type-var]
        # The rows are matched to products by number only. Numbering that is not exactly
        # 1..n (0-based, a gap, a repeat) would put answers on the wrong products.
        why = f"answer numbering is not 1..{len(batch)}: got {indices}"
        return [Result(p.name, p.category, None, "invalid", why) for p in batch]
    rows: dict[int, dict[str, Any]] = {row["i"]: row for row in raw_rows}

    results = []
    for number, product in enumerate(batch, start=1):
        row = rows[number]
        why = str(row.get("why") or "").strip()
        match = row.get("m")
        raw = row.get("e")
        emoji = known.get(str(raw).replace(VARIATION_SELECTOR, "")) if raw else None
        if match not in MATCHES:
            results.append(
                Result(product.name, product.category, None, "invalid", f"m={match!r}")
            )
        elif match == "none":
            # A "none" that still names an emoji is the closest match: drop it.
            results.append(Result(product.name, product.category, None, "none", why))
        elif raw is None or emoji is None:
            detail = "no emoji" if raw is None else f"answered {raw} outside the list"
            results.append(
                Result(
                    product.name,
                    product.category,
                    None,
                    "invalid",
                    f"{match} with {detail}: {why}",
                )
            )
        else:
            results.append(Result(product.name, product.category, emoji, match, why))
    return results


def count(results: list[Result]) -> dict[str, int]:
    return {outcome: sum(r.match == outcome for r in results) for outcome in OUTCOMES}


def run(
    products: list[Product],
    reference: list[dict[str, Any]],
    complete: Callable[[list[Product]], str],
    batch_size: int,
    on_batch: Callable[[list[Result]], None] | None = None,
) -> list[Result]:
    """Ask about every product, one batch after another (the gateway serves one request).

    `on_batch` gets the results so far after every batch, so a caller can write them out
    and a crash or a closed console loses at most the batch in flight.
    """
    results: list[Result] = []
    for start in range(0, len(products), batch_size):
        batch = products[start : start + batch_size]
        started = time.monotonic()
        try:
            content = complete(batch)
        except GatewayError as exc:
            print(
                f"  batch {start // batch_size + 1}: request failed: {exc}", flush=True
            )
            results.extend(
                Result(p.name, p.category, None, "missing", f"request failed: {exc}")
                for p in batch
            )
            if on_batch:
                on_batch(results)
            continue
        answered = parse_answers(content, batch, reference)
        results.extend(answered)
        counts = count(answered)
        print(
            f"  batch {start // batch_size + 1}: {len(batch)} products "
            f"in {time.monotonic() - started:.1f}s  "
            + " ".join(f"{k}={v}" for k, v in counts.items() if v),
            flush=True,
        )
        if on_batch:
            on_batch(results)
    return results


# --- output ------------------------------------------------------------------------------


def _cell(value: str | None) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")


def _table(results: list[Result]) -> list[str]:
    lines = ["| Product | Category | Emoji | Why |", "| --- | --- | --- | --- |"]
    lines += [
        f"| {_cell(r.name)} | {_cell(r.category)} | {_cell(r.emoji)} | {_cell(r.why)} |"
        for r in results
    ]
    return lines


def render_markdown(results: list[Result], title: str) -> str:
    counts = count(results)
    lines = [
        f"# {title}",
        "",
        " · ".join(f"{k} {v}" for k, v in counts.items()) + f" · total {len(results)}",
        "",
    ]
    sections = (
        ("Exact", "exact"),
        ("Borderline (operator ruling needed)", "borderline"),
        ("None", "none"),
        ("Invalid answers", "invalid"),
        ("Missing answers", "missing"),
    )
    for heading, outcome in sections:
        chosen = [r for r in results if r.match == outcome]
        if chosen:
            lines += [f"## {heading} ({len(chosen)})", "", *_table(chosen), ""]
    gap = [r for r in results if r.match != "exact"]
    lines += [
        f"## Gap list ({len(gap)})",
        "",
        "Products without an exact emoji; borderline ones stay here until the operator rules.",
        "",
    ]
    lines += [f"- {r.name}" + (f" ({r.category})" if r.category else "") for r in gap]
    return "\n".join(lines) + "\n"


def write_outputs(results: list[Result], out: Path, title: str) -> list[Path]:
    """The Markdown at `out`, plus CSV and JSON beside it with the same stem."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(results, title), encoding="utf-8")
    csv_path = out.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["name", "category", "emoji", "match", "why"]
        )
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "name": r.name,
                    "category": r.category or "",
                    "emoji": r.emoji or "",
                    "match": r.match,
                    "why": r.why,
                }
            )
    json_path = out.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {"counts": count(results), "results": [asdict(r) for r in results]},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return [out, csv_path, json_path]


# --- the command -------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--names", type=Path, help="CSV `name,category` or bare names")
    source.add_argument(
        "--from-db", action="store_true", help="read the product catalog"
    )
    source.add_argument(
        "--build-reference",
        type=Path,
        metavar="EMOJI_TEST",
        help="regenerate scripts/emoji_food.json from emoji-test.txt",
    )
    parser.add_argument("--out", type=Path, default=Path("emoji_trial.md"))
    parser.add_argument(
        "--url", help="OpenAI-compatible base URL (default LLM_BASE_URL)"
    )
    parser.add_argument("--model", help="model name (default LLM_MODEL)")
    parser.add_argument(
        "--reasoning",
        choices=("low", "medium", "high", "xhigh", "off"),
        help="reasoning_strength (default LLM_REASONING_STRENGTH)",
    )
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument(
        "--timeout", type=float, help="seconds a request (default LLM_TIMEOUT)"
    )
    parser.add_argument(
        "--limit", type=int, help="--from-db: read at most this many products"
    )
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--cutoff", default=DEFAULT_CUTOFF, help="newest Emoji version")
    parser.add_argument("--title", default="Q18 exact-emoji trial")
    args = parser.parse_args(argv)

    if args.build_reference:
        data = build_reference(
            args.build_reference.read_text(encoding="utf-8"), cutoff=args.cutoff
        )
        write_reference(data)
        print(
            f"{len(data['emoji'])} emoji (Emoji {data['unicode_emoji_version']}, "
            f"cutoff {data['cutoff']}, {len(data['excluded_newer'])} newer left out) "
            f"-> {REFERENCE_FILE}"
        )
        return 0

    from app.core.config import settings

    if args.from_db:
        products = asyncio.run(_read_catalog(args.limit))
    else:
        products = read_names(args.names)
    reference = load_reference_file()["emoji"]
    model = args.model or settings.LLM_MODEL
    url = args.url or settings.LLM_BASE_URL
    reasoning = (
        settings.LLM_REASONING_STRENGTH if args.reasoning is None else args.reasoning
    )
    reasoning = None if reasoning == "off" else reasoning
    timeout = settings.LLM_TIMEOUT if args.timeout is None else args.timeout
    print(
        f"{len(products)} products, {len(reference)} emoji, model {model}, "
        f"reasoning {reasoning}, batches of {args.batch_size}, timeout {timeout:.0f}s"
    )

    def complete(batch: list[Product]) -> str:
        payload = build_payload(
            build_prompt(batch, reference), model, reasoning, args.max_tokens
        )
        return post_chat(
            payload, url=url, api_key=settings.LLM_API_KEY, timeout=timeout
        )

    # Written after every batch, so a crash keeps what was finished.
    results = run(
        products,
        reference,
        complete,
        args.batch_size,
        on_batch=lambda so_far: write_outputs(so_far, args.out, args.title),
    )
    written = write_outputs(results, args.out, args.title)
    print(" ".join(f"{k}={v}" for k, v in count(results).items()))
    print("wrote " + ", ".join(str(p) for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
