"""MVP-R0 extraction spike harness (results recorded in docs/vLLM_MANUAL_TEST.md).

Run with the backend venv (needs httpx, rapidfuzz, Pillow) from any directory, e.g.
  backend/.venv/Scripts/python docs/spikes/r0_extraction_spike.py run muse-glimmer text \\
      --compact --rs low
Outputs (rendered image, raw replies, scored JSON) go to <tempdir>/kyokki_r0/.
Set R0_GATEWAY to target another OpenAI-compatible server.

Usage:
  r0_extraction_spike.py truth
  r0_extraction_spike.py render
  r0_extraction_spike.py warm <model>
  r0_extraction_spike.py run <model> <text|vision> [--compact] [--rs STRENGTH]
      [--no-schema] [--think] [--full-prompt] [--tag X]
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import pathlib
import re
import sys
import tempfile
import time

import httpx
from rapidfuzz import fuzz

HERE = pathlib.Path(tempfile.gettempdir()) / "kyokki_r0"
HERE.mkdir(exist_ok=True)
DOC = pathlib.Path(__file__).resolve().parents[1] / "vLLM_MANUAL_TEST.md"
GATEWAY = os.environ.get("R0_GATEWAY", "http://192.168.0.94:9292")
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- data
def receipt_text() -> str:
    doc = DOC.read_text(encoding="utf-8")
    section = doc[doc.index("## Test 2: Real Receipt") :]
    body = section[
        section.index("Receipt text:\n```\n") + len("Receipt text:\n```\n") :
    ]
    return body[: body.index("\n```")]


PRICE_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<price>-?\d+,\d{2})(?:\s+\d+,\d{2})?$")
QTY_LINE = re.compile(r"^(?P<n>\d+)\s+KPL\b")
KG_LINE = re.compile(r"^(?P<kg>\d+,\d{3})\s+KG\b")
FEES = ("VERKKOK.PAKKAUSMATERIAALIMAKSU", "TOIMITUSMAKSU")
NON_FOOD = (
    "KOMPOSTOINTIPUSSI",
    "ROSKAPUSSI",
    "PYYKKIETIKKA",
    "NESTESAIPPUA",
    "SIENILIINA",
    "KEITTIÖSUIHKE",
    "YLEISPUHDISTUSSUIHKE",
)


def ground_truth() -> list[dict]:
    lines = receipt_text().splitlines()
    start = lines.index("-" * 40) + 1
    end = lines.index("-" * 40, start)
    items: list[dict] = []
    for line in lines[start:end]:
        line = line.strip()
        if q := QTY_LINE.match(line):
            items[-1]["quantity"] = int(q["n"])
            continue
        if k := KG_LINE.match(line):
            items[-1]["weight_kg"] = float(k["kg"].replace(",", "."))
            continue
        if line.startswith(("NORM.", "ALENNUS")):
            continue
        m = PRICE_LINE.match(line)
        if not m or m["name"].startswith(FEES):
            continue
        items.append(
            {
                "name": m["name"],
                "quantity": 1,
                "weight_kg": None,
                "food": not any(word in m["name"] for word in NON_FOOD),
            }
        )
    return items


SKIP = re.compile(
    r"^(-{5,}|VÄLISUMMA|YHTEENSÄ|BONUSTA|MAKSUTAPA|Kortti:|\*{4,}|Veloitus:|Autentisointi:|"
    r"Viite:|Aika:|ALV\b|\d+,\d+%|YHT\.|NORM\.|ALENNUS|TOIMITUSMAKSU|VERKKOK\.PAKKAUS)"
)


def prefiltered_text() -> str:
    return "\n".join(
        line for line in receipt_text().splitlines() if not SKIP.match(line.strip())
    )


TRIMMED_INSTRUCTIONS = """Extract every purchased product from this Finnish grocery receipt.

Rules:
- One entry per product line. Keep the product name exactly as written, without the price.
- A following line like "3 KPL 1,88 €/KPL" means quantity 3 of the product above it.
- A following line like "0,386 KG 3,89 €/KG" means the product above it weighs 0.386 kg.
- Otherwise quantity is 1 and weight_kg is null.
- unit is "pcs" for counted items and "kg" for items sold by weight.
- Skip store header, totals, discounts (NORM., ALENNUS), fees, payment and VAT lines.

Return only JSON matching the schema: {"products": [{"name", "quantity", "unit", "weight_kg", "volume_l"}]}."""

SCHEMA = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string", "enum": ["pcs", "kg", "l"]},
                    "weight_kg": {"type": ["number", "null"]},
                    "volume_l": {"type": ["number", "null"]},
                },
                "required": ["name", "quantity", "unit", "weight_kg", "volume_l"],
            },
        }
    },
    "required": ["products"],
}


COMPACT_INSTRUCTIONS = """Extract every purchased product from this Finnish grocery receipt.

Rules:
- One entry per product line. n = the product name exactly as written, without the price.
- A following line like "3 KPL 1,88 €/KPL" means q = 3 for the product above it.
- A following line like "0,386 KG 3,89 €/KG" means w = 0.386 (kg) for the product above it.
- Otherwise q = 1 and w = null.
- Skip store header, totals, discounts (NORM., ALENNUS), fees, payment and VAT lines.

Return only compact JSON: {"p": [{"n": name, "q": quantity, "w": weight_kg or null}]}."""

COMPACT_SCHEMA = {
    "type": "object",
    "properties": {
        "p": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "string"},
                    "q": {"type": "number"},
                    "w": {"type": ["number", "null"]},
                },
                "required": ["n", "q", "w"],
            },
        }
    },
    "required": ["p"],
}


def full_prompt() -> str:
    doc = DOC.read_text(encoding="utf-8")
    section = doc[doc.index("## Test 2: Real Receipt") :]
    body = section[section.index("### Prompt:\n```\n") + len("### Prompt:\n```\n") :]
    return body[: body.index("\n```\n\n### Problem")]


# --------------------------------------------------------------------------- image
IMAGE = HERE / "receipt.png"


def render() -> None:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    text = receipt_text().splitlines()
    font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 26)
    line_h = 32
    width, height = 760, line_h * len(text) + 80
    img = Image.new("L", (width, height), 250)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(text):
        draw.text((30, 40 + i * line_h), line, fill=25, font=font)
    img = img.rotate(1.2, expand=True, fillcolor=235).filter(
        ImageFilter.GaussianBlur(0.6)
    )
    # phone-camera-like downscale: long edge 2000 px (what R6 will upload)
    scale = 2000 / max(img.size)
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    img.convert("RGB").save(IMAGE, optimize=True)
    print(IMAGE, img.size, IMAGE.stat().st_size, "bytes")


# --------------------------------------------------------------------------- scoring
TRAILING_PRICE = re.compile(r"\s+-?\d+[,.]\d{2}(\s*€)?$")


def norm(s: str) -> str:
    return TRAILING_PRICE.sub("", re.sub(r"\s+", " ", s.upper()).strip())


def score(products: list[dict]) -> dict:
    truth = ground_truth()
    used: set[int] = set()
    matched = []
    for t_idx, t in enumerate(truth):
        best, best_i = 0.0, None
        for i, p in enumerate(products):
            if i in used or not isinstance(p, dict) or not p.get("name"):
                continue
            s = fuzz.ratio(norm(t["name"]), norm(str(p["name"])))
            if s > best:
                best, best_i = s, i
        if best_i is not None and best >= 80:
            used.add(best_i)
            matched.append((t_idx, best_i))
    qty_ok = weight_ok = qty_total = weight_total = 0
    for t_idx, p_idx in matched:
        t, p = truth[t_idx], products[p_idx]
        if t["weight_kg"] is not None:
            weight_total += 1
            with contextlib.suppress(TypeError, ValueError):
                weight_ok += (
                    abs(float(p.get("weight_kg") or 0) - t["weight_kg"]) < 0.002
                )
        elif t["quantity"] != 1:
            qty_total += 1
            with contextlib.suppress(TypeError, ValueError):
                qty_ok += float(p.get("quantity") or 0) == t["quantity"]
    food = [i for i, t in enumerate(truth) if t["food"]]
    return {
        "expected": len(truth),
        "returned": len(products),
        "matched": len(matched),
        "recall": round(len(matched) / len(truth), 3),
        "food_recall": round(sum(1 for t, _ in matched if t in food) / len(food), 3),
        "extra": len(products) - len(matched),
        "names_with_price": sum(
            1
            for p in products
            if isinstance(p, dict) and TRAILING_PRICE.search(str(p.get("name", "")))
        ),
        "qty_ok": f"{qty_ok}/{qty_total}",
        "weight_ok": f"{weight_ok}/{weight_total}",
        "missed": [
            truth[i]["name"]
            for i in range(len(truth))
            if i not in {t for t, _ in matched}
        ],
    }


def parse_json(content: str) -> dict | None:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.S)
    if fence:
        content = fence.group(1)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- calls
def post(payload: dict, timeout: float) -> tuple[dict, float]:
    t0 = time.monotonic()
    r = httpx.post(f"{GATEWAY}/v1/chat/completions", json=payload, timeout=timeout)
    elapsed = time.monotonic() - t0
    try:
        body = r.json()
    except ValueError:
        body = {"error": r.text[:500]}
    body["_status"] = r.status_code
    return body, elapsed


def warm(model: str) -> None:
    body, elapsed = post(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Say OK."}],
            "max_tokens": 5,
        },
        timeout=1000,
    )
    print(
        json.dumps(
            {
                "model": model,
                "warm_seconds": round(elapsed, 1),
                "status": body["_status"],
                "reply": (body.get("choices") or [{}])[0]
                .get("message", {})
                .get("content"),
            }
        )
    )


def run(model: str, mode: str, flags: list[str]) -> None:
    use_schema = "--no-schema" not in flags
    think = "--think" in flags
    tag = flags[flags.index("--tag") + 1] if "--tag" in flags else ""

    compact = "--compact" in flags
    instructions = COMPACT_INSTRUCTIONS if compact else TRIMMED_INSTRUCTIONS
    if "--full-prompt" in flags:
        text_part = full_prompt()
    elif mode == "text":
        text_part = f"{instructions}\n\nReceipt:\n{prefiltered_text()}"
    else:
        text_part = instructions

    if mode == "vision":
        b64 = base64.b64encode(IMAGE.read_bytes()).decode()
        content: object = [
            {"type": "text", "text": text_part},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]
    else:
        content = text_part

    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 4096,
        "temperature": 0.2,
    }
    kwargs: dict = {}
    if not think:
        kwargs["enable_thinking"] = False
    if "--rs" in flags:
        kwargs["reasoning_strength"] = flags[flags.index("--rs") + 1]
    if kwargs:
        payload["chat_template_kwargs"] = kwargs
    if use_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "receipt",
                "schema": COMPACT_SCHEMA if compact else SCHEMA,
                "strict": True,
            },
        }

    body, elapsed = post(payload, timeout=600)
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message", {}) or {}
    content_out = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    usage = body.get("usage", {})
    parsed = parse_json(content_out)
    products = parsed.get("products", []) if isinstance(parsed, dict) else []
    if compact and isinstance(parsed, dict):
        products = [
            {"name": x.get("n"), "quantity": x.get("q"), "weight_kg": x.get("w")}
            for x in parsed.get("p", [])
            if isinstance(x, dict)
        ]
    result = {
        "model": model,
        "mode": mode,
        "schema": use_schema,
        "thinking": think,
        "tag": tag,
        "status": body["_status"],
        "error": body.get("error"),
        "seconds": round(elapsed, 1),
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_chars": len(reasoning),
        "json_ok": parsed is not None,
        **(score(products) if parsed is not None else {}),
    }
    stamp = f"{model}_{mode}{'_schema' if use_schema else ''}{'_think' if think else ''}{('_' + tag) if tag else ''}"
    (RESULTS / f"{stamp}.raw.txt").write_text(
        content_out + ("\n\n--- reasoning ---\n" + reasoning if reasoning else ""),
        encoding="utf-8",
    )
    (RESULTS / f"{stamp}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {k: v for k, v in result.items() if k != "missed"}
    summary["missed_n"] = len(result.get("missed", []))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "truth":
        truth = ground_truth()
        print(len(truth), "products;", sum(t["food"] for t in truth), "food")
        for t in truth:
            print(t)
        print("--- prefiltered ---")
        print(prefiltered_text())
    elif cmd == "render":
        render()
    elif cmd == "warm":
        warm(sys.argv[2])
    elif cmd == "run":
        run(sys.argv[2], sys.argv[3], sys.argv[4:])
