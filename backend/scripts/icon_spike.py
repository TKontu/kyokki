"""Q18 spike: can the model give every product its own icon?

Two routes, run on the product fixture in `tests/fixtures/icon_spike/products.json`:

- `--route pick`: the model picks the best icon for a product from one curated open SVG set
  (the food and drink subset of OpenMoji, vendored in `frontend/public/icon-spike/openmoji/`),
  or `null` when none fits.
- `--route draw`: the model writes a flat 48x48 SVG itself. The answer is parsed with a real
  XML parser and everything off a small allowlist is dropped before it is saved.

Both write into `frontend/public/icon-spike/results.json`, keyed by product name, which the
comparison page `/components-demo/icons` reads. `--route vendor` (re)downloads the OpenMoji
subset. This is a spike tool, not part of the app: nothing imports it and no test runs it.

    python -m scripts.icon_spike --route vendor
    python -m scripts.icon_spike --route pick --model c2.qwen3.8-27b
    python -m scripts.icon_spike --route draw --model c2.qwen3.8-27b --only "Rye bread"

Model calls run one after another: the gateway serves one request at a time.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
FIXTURE = BACKEND / "tests" / "fixtures" / "icon_spike" / "products.json"
PUBLIC = REPO / "frontend" / "public" / "icon-spike"
SET_DIR = PUBLIC / "openmoji"
GENERATED = PUBLIC / "generated"
RESULTS = PUBLIC / "results.json"

OPENMOJI_VERSION = "17.0.0"
OPENMOJI_CDN = f"https://cdn.jsdelivr.net/npm/openmoji@{OPENMOJI_VERSION}"
# OpenMoji's food and drink: the Unicode food-drink group without dishware, plus OpenMoji's
# own food extras (boule bread, pretzel, roasted coffee bean, jars, ...).
VENDOR_GROUPS = {"food-drink", "extras-openmoji", "extras-unicode"}
VENDOR_SKIP_SUBGROUPS = {"dishware"}

SVG_NS = "http://www.w3.org/2000/svg"
ALLOWED_ELEMENTS = {
    "svg",
    "g",
    "path",
    "circle",
    "ellipse",
    "rect",
    "polygon",
    "polyline",
    "line",
}
ALLOWED_ATTRIBUTES = {
    # geometry
    "viewBox",
    "width",
    "height",
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
    "d",
    "points",
    "transform",
    # presentation
    "fill",
    "fill-opacity",
    "fill-rule",
    "clip-rule",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-opacity",
    "stroke-dasharray",
    "opacity",
}
# A colour value: a hex colour or `none`. Anything else (url(#...), currentColor, names) is
# dropped, so a fill cannot point at a gradient or an external resource.
COLOUR = re.compile(r"^(#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|none)$")
COLOUR_ATTRIBUTES = {"fill", "stroke"}

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

PICK_PROMPT = """You choose an icon for a product in a kitchen inventory app.

Product: {name} (category: {category})

Available icons, one per line as `id: name (tags)`:
{icons}

Pick the icon that best shows this product itself, so that someone glancing at a fridge
screen recognises it. A close stand-in is fine (for example a similar-looking item), but
answer null when nothing would be recognised as this product.

Answer with JSON only: {{"icon": "<id>" or null, "reason": "<a few words>"}}"""


def load_products(only: list[str] | None) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))[
        "products"
    ]
    if only:
        wanted = {name.lower() for name in only}
        products = [p for p in products if p["name"].lower() in wanted]
    return products


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# --- the model ---------------------------------------------------------------------------


def gateway_url() -> str:
    """The gateway URL from the app settings; `--url` overrides it."""
    from app.core.config import settings

    return settings.LLM_BASE_URL


def chat(
    client: httpx.Client, url: str, model: str, prompt: str, max_tokens: int
) -> str:
    response = client.post(
        f"{url.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"].get("content") or ""
    return str(content)


# --- results.json ------------------------------------------------------------------------


def load_results() -> dict[str, Any]:
    if RESULTS.exists():
        results: dict[str, Any] = json.loads(RESULTS.read_text(encoding="utf-8"))
        return results
    return {"products": []}


def save_results(results: dict[str, Any], products: list[dict[str, Any]]) -> None:
    # Keep the fixture's order, so the page and the doc list products the same way.
    order = [
        p["name"] for p in json.loads(FIXTURE.read_text(encoding="utf-8"))["products"]
    ]
    by_name = {p["name"]: p for p in results["products"]}
    for product in products:
        entry = by_name.setdefault(product["name"], {})
        entry.update(
            name=product["name"],
            category=product["category"],
            category_icon=product["category_icon"],
        )
    results["products"] = [by_name[name] for name in order if name in by_name]
    RESULTS.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def entry_for(results: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
    for entry in results["products"]:
        if entry["name"] == product["name"]:
            return entry
    entry = {"name": product["name"]}
    results["products"].append(entry)
    return entry


# --- route (a): pick ---------------------------------------------------------------------


def load_index() -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = json.loads(
        (SET_DIR / "index.json").read_text(encoding="utf-8")
    )
    return index


def icon_line(icon: dict[str, Any]) -> str:
    tags = ", ".join(t for t in (icon["tags"], icon["openmoji_tags"]) if t)
    return f"{icon['id']}: {icon['annotation']}" + (f" ({tags})" if tags else "")


def parse_pick(text: str, ids: set[str]) -> tuple[str | None, str, bool]:
    """(icon id or None, reason, whether the answer was valid JSON naming a known id)."""
    # Take the last JSON object that has an "icon" key: reasoning text before the answer may
    # contain braces of its own, which a greedy `{.*}` would swallow into invalid JSON.
    decoder = json.JSONDecoder()
    answer: dict[str, Any] | None = None
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "icon" in value:
            answer = value
    if answer is None:
        return None, "", False
    icon = answer.get("icon")
    reason = str(answer.get("reason") or "")
    if icon is None:
        return None, reason, True
    icon = str(icon).upper()
    return (icon, reason, True) if icon in ids else (None, reason, False)


def run_pick(
    client: httpx.Client, url: str, model: str, products: list[dict[str, Any]]
) -> None:
    index = load_index()
    by_id = {icon["id"]: icon for icon in index}
    icons = "\n".join(icon_line(icon) for icon in index)
    results = load_results()
    for product in products:
        prompt = PICK_PROMPT.format(
            name=product["name"], category=product["category"], icons=icons
        )
        started = time.perf_counter()
        text = chat(client, url, model, prompt, max_tokens=4096)
        latency = round(time.perf_counter() - started, 1)
        icon, reason, valid = parse_pick(text, set(by_id))
        pick: dict[str, Any] = {
            "icon": icon,
            "file": f"/icon-spike/openmoji/{icon}.svg" if icon else None,
            "annotation": by_id[icon]["annotation"] if icon else None,
            "emoji": by_id[icon]["emoji"] if icon else None,
            "reason": reason,
            "valid_answer": valid,
            "latency_s": latency,
        }
        entry_for(results, product)["pick"] = pick
        print(
            f"pick  {product['name']:<24} {icon or 'null':<8} {pick['annotation'] or ''} {latency}s"
        )
    save_results(results, products)


# --- route (b): draw ---------------------------------------------------------------------


def local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def sanitise(svg_text: str) -> tuple[str, bool]:
    """Parse the model's SVG and keep only the allowlist. Returns (clean SVG, changed).

    Raises ValueError when there is no parseable <svg> root. Disallowed elements are dropped
    with their whole subtree; disallowed attributes (event handlers, href, style, class, id,
    colours that are not plain hex) are dropped from the elements that stay.
    """
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise ValueError(f"not well-formed XML: {exc}") from exc
    if local(root.tag) != "svg":
        raise ValueError(f"root element is <{local(root.tag)}>, not <svg>")

    changed = False

    def clean(element: ET.Element) -> ET.Element:
        nonlocal changed
        out = ET.Element(local(element.tag))
        for name, value in element.attrib.items():
            if name.startswith("{") or name == "xmlns":
                changed = changed or name != "xmlns"
                continue
            if name not in ALLOWED_ATTRIBUTES:
                changed = True
                continue
            if name in COLOUR_ATTRIBUTES and not COLOUR.match(value.strip()):
                changed = True
                continue
            out.set(name, value)
        if (element.text or "").strip():
            changed = True
        for child in element:
            if local(child.tag) in ALLOWED_ELEMENTS and local(child.tag) != "svg":
                out.append(clean(child))
            else:
                changed = True
        return out

    cleaned = clean(root)
    if cleaned.get("viewBox") != "0 0 48 48":
        changed = True
        cleaned.set("viewBox", "0 0 48 48")
    cleaned.set("xmlns", SVG_NS)
    if not len(cleaned):
        raise ValueError("nothing drawable left after sanitising")
    return ET.tostring(cleaned, encoding="unicode"), changed


def extract_svg(text: str) -> str | None:
    match = re.search(r"<svg\b.*?</svg>", text, re.DOTALL | re.IGNORECASE)
    return match.group(0) if match else None


def run_draw(
    client: httpx.Client,
    url: str,
    model: str,
    products: list[dict[str, Any]],
    attempts: int,
) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    palette = ", ".join(f"{name} {hexcode}" for name, hexcode in PALETTE.items())
    results = load_results()
    for product in products:
        prompt = DRAW_PROMPT.format(
            name=product["name"], category=product["category"], palette=palette
        )
        tries: list[dict[str, Any]] = []
        draw: dict[str, Any] = {
            "file": None,
            "parsed": False,
            "sanitised_changed": None,
        }
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                text = chat(client, url, model, prompt, max_tokens=8192)
            except httpx.HTTPError as exc:
                tries.append({"attempt": attempt, "error": f"http: {exc}"})
                continue
            latency = round(time.perf_counter() - started, 1)
            raw = extract_svg(text)
            if raw is None:
                tries.append(
                    {"attempt": attempt, "latency_s": latency, "error": "no <svg>"}
                )
                continue
            try:
                clean, changed = sanitise(raw)
            except ValueError as exc:
                tries.append(
                    {"attempt": attempt, "latency_s": latency, "error": str(exc)}
                )
                continue
            tries.append({"attempt": attempt, "latency_s": latency, "error": None})
            path = GENERATED / f"{slug(product['name'])}.svg"
            path.write_text(clean + "\n", encoding="utf-8")
            draw = {
                "file": f"/icon-spike/generated/{path.name}",
                "parsed": True,
                "sanitised_changed": changed,
                "bytes": len(clean),
            }
            break
        if draw["file"] is None:
            # A failed re-draw must not leave an earlier run's SVG behind: disk has to match
            # results.json, which now says `file: null`.
            (GENERATED / f"{slug(product['name'])}.svg").unlink(missing_ok=True)
        draw["attempts"] = tries
        draw["latency_s"] = round(sum(t.get("latency_s", 0) for t in tries), 1)
        entry_for(results, product)["draw"] = draw
        status = draw["file"] or "failed"
        print(
            f"draw  {product['name']:<24} {status} {draw['latency_s']}s x{len(tries)}"
        )
    save_results(results, products)


# --- vendoring the set -------------------------------------------------------------------


def minify_svg(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r">\s+<", "><", text)
    return text.strip() + "\n"


def run_vendor(client: httpx.Client) -> None:
    data = client.get(f"{OPENMOJI_CDN}/data/openmoji.json").raise_for_status().json()
    chosen = [
        e
        for e in data
        if e["group"] in VENDOR_GROUPS
        and ("food" in e["subgroups"] or "drink" in e["subgroups"])
        and e["subgroups"] not in VENDOR_SKIP_SUBGROUPS
    ]
    SET_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for e in chosen:
        svg = (
            client.get(f"{OPENMOJI_CDN}/color/svg/{e['hexcode']}.svg")
            .raise_for_status()
            .text
        )
        (SET_DIR / f"{e['hexcode']}.svg").write_text(minify_svg(svg), encoding="utf-8")
        index.append(
            {
                "id": e["hexcode"],
                "emoji": e["emoji"],
                "annotation": e["annotation"],
                "tags": e["tags"],
                "openmoji_tags": e["openmoji_tags"],
                "group": e["group"],
                "subgroup": e["subgroups"],
            }
        )
    (SET_DIR / "index.json").write_text(
        "[\n" + ",\n".join(json.dumps(i, ensure_ascii=False) for i in index) + "\n]\n",
        encoding="utf-8",
    )
    print(f"vendored {len(index)} OpenMoji {OPENMOJI_VERSION} icons into {SET_DIR}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--route", choices=("pick", "draw", "vendor"), required=True)
    parser.add_argument(
        "--url", help="OpenAI-compatible base URL (default: LLM_BASE_URL)"
    )
    parser.add_argument(
        "--model",
        help="model name, required for pick and draw (the spike used c2.qwen3.8-27b)",
    )
    parser.add_argument("--only", action="append", help="run one product (repeatable)")
    parser.add_argument(
        "--attempts", type=int, default=2, help="draw attempts per product"
    )
    args = parser.parse_args(argv)

    with httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
        if args.route == "vendor":
            run_vendor(client)
            return 0
        if not args.model:
            # No fallback to LLM_MODEL: it names a different gateway slot from the spike's.
            parser.error("--model is required for --route pick and --route draw")
        model = args.model
        url = args.url or gateway_url()
        products = load_products(args.only)
        results = load_results()
        results.setdefault("runs", {})[args.route] = {
            "model": model,
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        save_results(results, [])
        if args.route == "pick":
            run_pick(client, url, model, products)
        else:
            run_draw(client, url, model, products, args.attempts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
