"""Q18-S2 icon style spike: today's flat look against two candidate setups.

The operator called the generated icons "ugly and lazy" next to the emoji catalog (a red
bell pepper came out as a blank red silhouette). This script renders the same products at
the same seeds three ways so the operator can compare them on one contact sheet per seed:

- **S0 today:** ``build_icon_workflow(subject, seed=s)`` unchanged (flat trigger, 0.75).
- **S1 prompt:** trigger ``emoji`` at 0.4, a glossy-3D-emoji positive prompt, and a
  negative prompt that also rules out silhouettes, outlines and flat colour.
- **S2 prompt + style:** S1 plus the IP-Adapter reference (nodes 9-11) fed a style board of
  Microsoft Fluent Emoji 3D food images, ``weight_type`` = the server's style-transfer
  option, weight 0.8; the first three products are also rendered at weight 0.6.

Every graph starts from ``app.services.icon_workflow.build_icon_workflow`` and is adjusted
here only - no production module changes. Subjects come from
``app.services.product_icons.icon_subject`` exactly as production computes them. Jobs go
through ``app.services.comfyui`` (hold protocol, one job at a time), and before each
product's batch the script waits for ``/comfyui-hold/status`` to clear, reusing
``scripts.icon_style_trial.wait_for_a_clear_hold``.

    python -m scripts.icon_style_spike board --source-dir /scratch/fluent
    python -m scripts.icon_style_spike render --full-dir /scratch/full
    python -m scripts.icon_style_spike sheets

``board`` composes the style board from the downloaded Fluent PNGs; ``render`` renders,
writes the 256/64 px thumbnails, ``renders.json`` (prompts, weights, timings, failures) and
the contact sheets; ``sheets`` rebuilds the contact sheets from the committed thumbnails.
Full-size renders go to ``--full-dir`` and are never committed. COMFYUI_BASE_URL,
COMFYUI_TIMEOUT, COMFYUI_POLL_INTERVAL and LLM_API_KEY come from settings.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from scripts.icon_style_trial import THUMBNAIL_SIZES, slug, wait_for_a_clear_hold

from app.services import comfyui
from app.services.icon_workflow import NEGATIVE_PROMPT, build_icon_workflow
from app.services.product_icons import icon_subject

OUT_DIR = Path("../docs/spikes/q18_s2")
BOARD_NAME = "style_board.png"
BOARD_SIZE = 1024

# Twelve products: the ten the assignment names, plus Cottage cheese and Hot dog sausages
# from the Q18 subjects gap list (docs/spikes/q18_subjects/README.md).
PRODUCTS: tuple[str, ...] = (
    "Red bell pepper",
    "Quark",
    "Tomato puree",
    "Fish fingers",
    "Canned tuna",
    "Karelian pasty",
    "Leek",
    "Mineral water",
    "Oat drink",
    "Rye bread",
    "Cottage cheese",
    "Hot dog sausages",
)
# Two fixed seeds, the same across every setup.
SEEDS: tuple[int, ...] = (20261006, 20261007)
# The weight-0.6 sensitivity check runs on the first three products only.
SENSITIVITY_PRODUCTS = PRODUCTS[:3]

S1_TRIGGER = "emoji"
S1_LORA_STRENGTH = 0.4
S1_POSITIVE = (
    "emoji, {subject}, glossy 3D emoji icon, soft gradient shading, highlight, "
    "full colour, detailed, white background"
)
S1_NEGATIVE = (
    NEGATIVE_PROMPT
    + ", silhouette, monochrome, outline, line art, lineart, flat colour, blank, sketch"
)
S2_WEIGHT = 0.8
S2_SENSITIVITY_WEIGHT = 0.6
# What GET /object_info/IPAdapterAdvanced listed on a4.comfyui on 2026-10-06.
S2_WEIGHT_TYPE = "style transfer"

# Setup id -> column label on the contact sheet.
SHEET_COLUMNS: tuple[tuple[str, str], ...] = (
    ("s0", "S0 today (flat 0.75)"),
    ("s1", "S1 prompt (emoji 0.4)"),
    ("s2", f"S2 prompt + style (IPA {S2_WEIGHT})"),
)

# The Fluent Emoji 3D files the board is built from, in grid order (MIT, Microsoft).
FLUENT_SOURCES: tuple[str, ...] = (
    "assets/Tomato/3D/tomato_3d.png",
    "assets/Carrot/3D/carrot_3d.png",
    "assets/Cheese wedge/3D/cheese_wedge_3d.png",
    "assets/Bread/3D/bread_3d.png",
    "assets/Canned food/3D/canned_food_3d.png",
    "assets/Glass of milk/3D/glass_of_milk_3d.png",
    "assets/Red apple/3D/red_apple_3d.png",
    "assets/Broccoli/3D/broccoli_3d.png",
    "assets/Egg/3D/egg_3d.png",
)


@dataclass
class Job:
    product: str
    subject: str
    setup: str  # s0, s1, s2, s2w06
    seed: int


@dataclass
class Result:
    product: str
    subject: str
    setup: str
    seed: int
    positive: str
    negative: str
    lora_trigger: str
    lora_strength: float
    ipadapter_weight: float | None
    ipadapter_weight_type: str | None
    seconds: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


# --- the style board -----------------------------------------------------------------------


def build_board(source_dir: Path, out_path: Path) -> Path:
    """Compose the Fluent PNGs into one square grid on white, BOARD_SIZE px a side."""
    files = [source_dir / Path(p).name for p in FLUENT_SOURCES]
    cols = math.ceil(math.sqrt(len(files)))
    rows = math.ceil(len(files) / cols)
    cell = BOARD_SIZE // cols
    pad = cell // 12
    board = Image.new("RGB", (BOARD_SIZE, BOARD_SIZE), "white")
    y_offset = (BOARD_SIZE - rows * cell) // 2
    for index, path in enumerate(files):
        with Image.open(path) as source:
            image = source.convert("RGBA")
        image.thumbnail((cell - 2 * pad, cell - 2 * pad), Image.Resampling.LANCZOS)
        x = (index % cols) * cell + (cell - image.width) // 2
        y = y_offset + (index // cols) * cell + (cell - image.height) // 2
        board.paste(image, (x, y), image)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.save(out_path)
    return out_path


# --- the graphs ----------------------------------------------------------------------------


def build_setup_workflow(
    job: Job, reference_image: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The graph for one job, and the parameters it used (for the write-up)."""
    if job.setup == "s0":
        graph = build_icon_workflow(job.subject, seed=job.seed)
        return graph, {
            "positive": graph["3"]["inputs"]["text"],
            "negative": graph["4"]["inputs"]["text"],
            "lora_trigger": "flat",
            "lora_strength": graph["2"]["inputs"]["strength_model"],
            "ipadapter_weight": None,
            "ipadapter_weight_type": None,
        }

    use_reference = job.setup in ("s2", "s2w06")
    if use_reference and reference_image is None:
        raise ValueError(f"{job.setup} needs the uploaded style board")
    graph = copy.deepcopy(
        build_icon_workflow(
            job.subject,
            style="emoji",
            seed=job.seed,
            lora_strength=S1_LORA_STRENGTH,
            reference_image=reference_image if use_reference else None,
        )
    )
    positive = S1_POSITIVE.format(subject=job.subject)
    graph["3"]["inputs"]["text"] = positive
    graph["4"]["inputs"]["text"] = S1_NEGATIVE
    weight: float | None = None
    weight_type: str | None = None
    if use_reference:
        weight = S2_WEIGHT if job.setup == "s2" else S2_SENSITIVITY_WEIGHT
        weight_type = S2_WEIGHT_TYPE
        graph["11"]["inputs"]["weight"] = weight
        graph["11"]["inputs"]["weight_type"] = weight_type
    return graph, {
        "positive": positive,
        "negative": S1_NEGATIVE,
        "lora_trigger": S1_TRIGGER,
        "lora_strength": S1_LORA_STRENGTH,
        "ipadapter_weight": weight,
        "ipadapter_weight_type": weight_type,
    }


def plan() -> list[Job]:
    """Every job, grouped by product: 12 x 2 seeds x 3 setups + 3 x 2 at weight 0.6 = 78."""
    jobs: list[Job] = []
    for product in PRODUCTS:
        subject = icon_subject(product)
        for seed in SEEDS:
            setups = ["s0", "s1", "s2"]
            if product in SENSITIVITY_PRODUCTS:
                setups.append("s2w06")
            jobs += [Job(product, subject, setup, seed) for setup in setups]
    return jobs


def base_name(product: str, setup: str, seed: int) -> str:
    return f"{slug(product)}_{setup}_{seed}"


async def render_one(job: Job, reference_image: str | None, full_dir: Path) -> Result:
    graph, params = build_setup_workflow(job, reference_image)
    started = time.monotonic()
    error: str | None = None
    images: list[bytes] = []
    try:
        images = await comfyui.render(graph)
        if not images:
            error = "no images returned"
    except comfyui.ComfyUIError as exc:
        error = f"{type(exc).__name__}: {exc}"
    seconds = round(time.monotonic() - started, 1)
    if error is None:
        full_dir.mkdir(parents=True, exist_ok=True)
        (full_dir / f"{base_name(job.product, job.setup, job.seed)}.png").write_bytes(
            images[0]
        )
    return Result(**asdict(job), **params, seconds=seconds, error=error)


def write_thumbnails(full_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(full_path) as source:
        image = source.convert("RGBA")
    for size in THUMBNAIL_SIZES:
        image.resize((size, size), Image.Resampling.LANCZOS).save(
            out_dir / f"{full_path.stem}_{size}.png"
        )


# --- the contact sheets --------------------------------------------------------------------

LABEL_WIDTH = 190
HEADER_HEIGHT = 40
GAP = 8


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def contact_sheet(
    image_dir: Path,
    products: tuple[str, ...],
    seed: int,
    columns: tuple[tuple[str, str], ...],
    title: str,
) -> Image.Image:
    """Rows = products, columns = setups; each cell is the 256 px icon plus its 64 px copy."""
    cell_w = 256 + GAP + 64 + GAP
    cell_h = 256 + GAP
    width = LABEL_WIDTH + cell_w * len(columns)
    height = HEADER_HEIGHT * 2 + cell_h * len(products)
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    draw.text((GAP, GAP), title, fill="black", font=_font(18))
    for col, (_setup, label) in enumerate(columns):
        x = LABEL_WIDTH + col * cell_w
        draw.text((x, HEADER_HEIGHT + GAP), label, fill="black", font=_font(15))
    for row, product in enumerate(products):
        y = HEADER_HEIGHT * 2 + row * cell_h
        draw.line([(0, y), (width, y)], fill="#dddddd")
        draw.text((GAP, y + 120), product, fill="black", font=_font(15))
        for col, (setup, _label) in enumerate(columns):
            x = LABEL_WIDTH + col * cell_w
            stem = base_name(product, setup, seed)
            path_256 = image_dir / f"{stem}_256.png"
            path_64 = image_dir / f"{stem}_64.png"
            if not path_256.exists():
                draw.text((x + 90, y + 120), "(failed)", fill="red", font=_font(15))
                continue
            with Image.open(path_256) as big:
                big_rgba = big.convert("RGBA")
                sheet.paste(big_rgba, (x, y + GAP // 2), big_rgba)
            with Image.open(path_64) as small:
                small_rgba = small.convert("RGBA")
                sheet.paste(small_rgba, (x + 256 + GAP, y + 96), small_rgba)
    return sheet


def write_sheets(out_dir: Path) -> list[Path]:
    image_dir = out_dir / "icons"
    written: list[Path] = []
    for seed in SEEDS:
        sheet = contact_sheet(
            image_dir,
            PRODUCTS,
            seed,
            SHEET_COLUMNS,
            f"Q18-S2 contact sheet, seed {seed} (256 px with the 64 px copy beside it)",
        )
        path = out_dir / f"contact_sheet_seed{seed}.png"
        sheet.save(path, optimize=True)
        written.append(path)
        sens = contact_sheet(
            image_dir,
            SENSITIVITY_PRODUCTS,
            seed,
            (
                ("s1", "S1 (no reference)"),
                ("s2w06", f"S2 IPA {S2_SENSITIVITY_WEIGHT}"),
                ("s2", f"S2 IPA {S2_WEIGHT}"),
            ),
            f"Q18-S2 IP-Adapter weight sensitivity, seed {seed}",
        )
        path = out_dir / f"sensitivity_seed{seed}.png"
        sens.save(path, optimize=True)
        written.append(path)
    return written


def dump_renders(meta: dict[str, Any]) -> str:
    """renders.json with one result per line, so the diff stays small and greppable."""
    head = {k: v for k, v in meta.items() if k != "results"}
    rows = ",\n".join("    " + json.dumps(r) for r in meta.get("results", []))
    body = json.dumps(head, indent=2)[:-2]
    return f'{body},\n  "results": [\n{rows}\n  ]\n}}\n'


# --- the command ---------------------------------------------------------------------------


async def run_renders(
    full_dir: Path, out_dir: Path, poll_seconds: float, max_wait: float
) -> tuple[list[Result], dict[str, Any]]:
    board = (out_dir / BOARD_NAME).read_bytes()
    uploaded = await comfyui.upload_image("kyokki_q18_s2_style_board.png", board)
    subfolder = uploaded.get("subfolder") or ""
    reference = f"{subfolder}/{uploaded['name']}" if subfolder else uploaded["name"]
    print(f"uploaded the style board as {reference!r}", flush=True)

    results: list[Result] = []
    current_product: str | None = None
    for job in plan():
        if job.product != current_product:
            current_product = job.product
            await wait_for_a_clear_hold(
                poll_seconds=poll_seconds,
                max_wait_seconds=max_wait,
                on_wait=lambda status: print(
                    f"  hold open ({status}); waiting", flush=True
                ),
            )
        print(f"rendering {job.product} {job.setup} seed={job.seed}...", flush=True)
        result = await render_one(job, reference, full_dir)
        if result.ok:
            write_thumbnails(
                full_dir / f"{base_name(job.product, job.setup, job.seed)}.png",
                out_dir / "icons",
            )
            print(f"  -> {result.seconds:.1f}s", flush=True)
        else:
            print(f"  FAILED after {result.seconds:.1f}s: {result.error}", flush=True)
        results.append(result)
    return results, {"reference_image": reference}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0] if __doc__ else ""
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    board = sub.add_parser("board", help="compose the style board")
    board.add_argument("--source-dir", type=Path, required=True)
    render = sub.add_parser("render", help="render every job, then the sheets")
    render.add_argument("--full-dir", type=Path, required=True)
    render.add_argument("--poll-seconds", type=float, default=5.0)
    render.add_argument("--max-wait-seconds", type=float, default=900.0)
    sub.add_parser("sheets", help="rebuild the contact sheets from the thumbnails")
    args = parser.parse_args(argv)
    out_dir: Path = args.out_dir

    if args.command == "board":
        print(f"wrote {build_board(args.source_dir, out_dir / BOARD_NAME)}")
        return 0

    if args.command == "render":
        started = time.monotonic()
        results, meta = asyncio.run(
            run_renders(
                args.full_dir, out_dir, args.poll_seconds, args.max_wait_seconds
            )
        )
        meta["total_seconds"] = round(time.monotonic() - started, 1)
        meta["seeds"] = list(SEEDS)
        meta["results"] = [asdict(r) for r in results]
        (out_dir / "renders.json").write_text(dump_renders(meta), encoding="utf-8")
        ok = sum(1 for r in results if r.ok)
        print(f"{ok}/{len(results)} renders ok in {meta['total_seconds']}s")

    for path in write_sheets(out_dir):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
