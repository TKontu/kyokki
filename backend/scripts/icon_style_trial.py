"""Q18-G1 style trial: emoji vs flat, two seeds each, on ten gap-list products.

Renders the products in `docs/spikes/Q18_exact_emoji.md`'s "Gap list" that the operator gave
icon briefs for, plus a spread across other categories, in both LoRA styles
(`app.services.icon_workflow`), without the IP-Adapter reference. Every job goes through
`app.services.comfyui`, so the hold protocol, the one-job-per-base-URL lock and the >=1s
spacing all apply automatically; this script's own job is the product list, the two styles
and seeds, the PNG downscaling, and the write-up.

Before rendering, this script checks `GET /comfyui-hold/status` and waits for it to clear if
someone else is rendering - it never submits alongside another hold.

    python -m scripts.icon_style_trial --full-dir /path/to/scratch/full

Only `--full-dir` is required (a scratch directory for the full-size renders, never
committed); `--out` and `--image-dir` default to the committed doc and its image folder.
COMFYUI_BASE_URL, COMFYUI_TIMEOUT, COMFYUI_POLL_INTERVAL and LLM_API_KEY come from settings,
as they do for the client itself.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.services import comfyui
from app.services.icon_workflow import DEFAULT_LORA_STRENGTH, Style, build_icon_workflow

# The ten gap-list products (docs/spikes/Q18_exact_emoji.md "Gap list"): the four with an
# operator icon brief, plus six more spanning dairy, cheese, bread, meat, vegetables and
# drinks, as the assignment names them.
PRODUCTS: tuple[tuple[str, str | None], ...] = (
    ("Tomato puree", "a small can or squeeze out tube"),
    ("Canned tuna", "the tuna can as sold"),
    ("Fish fingers", "the fish fingers, or their pack, as sold"),
    ("Canned tomatoes", "a can, not a fresh tomato"),
    ("Quark", None),
    ("Mozzarella", None),
    ("Minced beef", None),
    ("Parsnip", None),
    ("Karelian pasty", None),
    ("Oat drink", None),
)

STYLES: tuple[Style, ...] = ("emoji", "flat")
# Two fixed seeds, deliberately not randomised: the point of the trial is a reproducible
# side-by-side, not a representative sample.
SEEDS: tuple[int, ...] = (20260930, 20260931)

THUMBNAIL_SIZES: tuple[int, ...] = (256, 64)


def build_subject(name: str, brief: str | None) -> str:
    """The product's generic name plus its icon brief, where the operator gave one."""
    return name if brief is None else f"{name}, {brief}"


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace(",", "").replace("/", "_")


@dataclass
class Job:
    product: str
    brief: str | None
    style: Style
    seed: int


@dataclass
class RenderResult:
    job: Job
    lora_strength: float
    seconds: float
    full_path: Path | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.full_path is not None


def plan() -> list[Job]:
    """Every (product, style, seed) job, in submission order: 10 x 2 x 2 = 40."""
    return [
        Job(name, brief, style, seed)
        for name, brief in PRODUCTS
        for style in STYLES
        for seed in SEEDS
    ]


async def wait_for_a_clear_hold(
    *,
    poll_seconds: float = 5.0,
    max_wait_seconds: float = 600.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_wait: Callable[[dict[str, object]], None] | None = None,
) -> None:
    """Block until `GET /comfyui-hold/status` shows no one else rendering.

    Raises TimeoutError if the hold never clears within `max_wait_seconds`. `on_wait` is
    called with each "still open" status, e.g. to print it.
    """
    waited = 0.0
    while True:
        status = await comfyui.hold_status()
        if not status.get("open"):
            return
        if on_wait is not None:
            on_wait(status)
        if waited >= max_wait_seconds:
            raise TimeoutError(
                f"ComfyUI's hold stayed open for {waited:.0f}s; giving up"
            )
        await sleep(poll_seconds)
        waited += poll_seconds


async def render_one(job: Job, full_dir: Path) -> RenderResult:
    """Render one job; on success, writes the full-size PNG to `full_dir` and returns it."""
    strength = DEFAULT_LORA_STRENGTH[job.style]
    workflow = build_icon_workflow(
        build_subject(job.product, job.brief), style=job.style, seed=job.seed
    )
    started = time.monotonic()
    try:
        images = await comfyui.render(workflow)
    except comfyui.ComfyUIError as exc:
        return RenderResult(
            job, strength, time.monotonic() - started, None, error=str(exc)
        )
    seconds = time.monotonic() - started
    if not images:
        return RenderResult(job, strength, seconds, None, error="no images returned")

    full_dir.mkdir(parents=True, exist_ok=True)
    full_path = full_dir / f"{slug(job.product)}_{job.style}_{job.seed}.png"
    full_path.write_bytes(images[0])
    return RenderResult(job, strength, seconds, full_path)


def write_thumbnails(full_path: Path, image_dir: Path, job: Job) -> dict[int, Path]:
    """256px and 64px copies of `full_path` under `image_dir`, keyed by side length."""
    image_dir.mkdir(parents=True, exist_ok=True)
    base = f"{slug(job.product)}_{job.style}_{job.seed}"
    written: dict[int, Path] = {}
    with Image.open(full_path) as source:
        image = source.convert("RGBA")
        for size in THUMBNAIL_SIZES:
            out_path = image_dir / f"{base}_{size}.png"
            image.resize((size, size), Image.LANCZOS).save(out_path)
            written[size] = out_path
    return written


# --- the write-up --------------------------------------------------------------------------

GRAPH_METHOD = """## Method

Every render used `app.services.icon_workflow.build_icon_workflow` (the frozen graph),
through `app.services.comfyui.render` (the hold protocol), against `a4.comfyui` on the GPU
host, over the SSH tunnel described in the assignment. No IP-Adapter reference image: nodes
9/10/11 were left out, so KSampler samples straight off the LoRA-loaded model.

Fixed graph parameters:

- Checkpoint: `sd_xl_base_1.0.safetensors`
- LoRA: `SDXL-Emoji-Lora-r4.safetensors`
- Canvas: 1024x1024, batch 1
- Sampler: `dpmpp_2m`, scheduler `karras`, cfg 7.0, denoise 1.0, 25 steps
- Negative prompt: "blurry, text, watermark"
- Background removal: `LoadRembgByBiRefNetModel` (`General.safetensors`) + `RembgByBiRefNet`

Per style:

| Style | Trigger word | LoRA strength used | Allowed range |
| --- | --- | --- | --- |
| emoji | `emoji` | 0.35 | 0.2 - 0.5 |
| flat | `flat` | 0.75 | 0.7 - 0.8 |

Two fixed seeds per style (20260930, 20260931), chosen for a reproducible side-by-side
rather than a representative sample.
"""


def _thumb_cell(image_dir_name: str, job: Job, size: int) -> str:
    path = f"{image_dir_name}/{slug(job.product)}_{job.style}_{job.seed}_{size}.png"
    return f"![{job.style} seed {job.seed} at {size}px]({path})"


def _product_table(
    product: str, results: list[RenderResult], image_dir_name: str
) -> list[str]:
    by_style_seed = {
        (r.job.style, r.job.seed): r for r in results if r.job.product == product
    }
    lines = [f"### {product}", ""]
    seeds = SEEDS
    header = "| | " + " | ".join(f"seed {s}" for s in seeds) + " |"
    lines.append(header)
    lines.append("| --- | " + " | ".join("---" for _ in seeds) + " |")
    for size in THUMBNAIL_SIZES:
        for style in STYLES:
            cells = []
            for seed in seeds:
                result = by_style_seed.get((style, seed))
                if result is None or not result.ok:
                    cells.append("(failed)")
                else:
                    cells.append(_thumb_cell(image_dir_name, result.job, size))
            lines.append(f"| {style} ({size}px) | " + " | ".join(cells) + " |")
        lines.append("")
    timing_bits = []
    for style in STYLES:
        for seed in seeds:
            result = by_style_seed.get((style, seed))
            if result is not None:
                mark = (
                    f"{result.seconds:.1f}s" if result.ok else f"FAILED: {result.error}"
                )
                timing_bits.append(f"{style}/{seed} {mark}")
    lines.append("Timings: " + ", ".join(timing_bits))
    lines.append("")
    return lines


def render_markdown(
    results: list[RenderResult], image_dir_name: str, cold_start_seconds: float | None
) -> str:
    lines = [
        "# Q18-G1 icon style trial: emoji vs flat",
        "",
        "Ten gap-list products, each rendered in both LoRA styles at two seeds, so the "
        "operator can pick a look before it is wired into the icon queue. The operator "
        "chooses; this document does not decide for them.",
        "",
        GRAPH_METHOD,
    ]
    if cold_start_seconds is not None:
        lines += [
            f"First job (cold start included): {cold_start_seconds:.1f}s. "
            "Later jobs measure steady-state render time only.",
            "",
        ]

    lines += ["## Renders", ""]
    seen: list[str] = []
    for result in results:
        if result.job.product not in seen:
            seen.append(result.job.product)
    for product in seen:
        lines += _product_table(product, results, image_dir_name)

    failures = [r for r in results if not r.ok]
    lines += [f"## Failures ({len(failures)})", ""]
    if failures:
        lines += ["| Product | Style | Seed | Error |", "| --- | --- | --- | --- |"]
        lines += [
            f"| {r.job.product} | {r.job.style} | {r.job.seed} | {r.error} |"
            for r in failures
        ]
    else:
        lines.append("None.")
    lines.append("")

    lines += [
        "## Reading the styles",
        "",
        "_Fill in after viewing the renders: which style sits better next to Apple emoji, "
        "and where each fails (unreadable at 64px, text artefacts, bad cut-outs)._",
        "",
        "## Recommended LoRA strength",
        "",
        "_Fill in per style, within the allowed range (emoji 0.2-0.5, flat 0.7-0.8)._",
        "",
        "## Next round",
        "",
        "Not implemented here. Wiring this into the product icon queue still needs:",
        "- PNG storage for a generated icon (where product_icons.py's SVGs live now, or "
        "a sibling column/table - out of this lane's scope, see product_icons.py).",
        "- Queue integration: call `build_icon_workflow` + `comfyui.render` for each gap "
        "product once the operator has picked a style.",
        "- A per-product Regenerate action that renders again with a new random seed.",
        "- Setting `COMFYUI_BASE_URL` in the real stack once the Kyokki server can reach "
        "the GPU host (a media-gateway is planned; see the assignment's Access section).",
        "",
    ]
    return "\n".join(lines) + "\n"


# --- the command ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0] if __doc__ else ""
    )
    parser.add_argument(
        "--out", type=Path, default=Path("docs/spikes/Q18_icon_styles.md")
    )
    parser.add_argument(
        "--image-dir", type=Path, default=Path("docs/spikes/q18_icon_styles")
    )
    parser.add_argument(
        "--full-dir",
        type=Path,
        required=True,
        help="scratch directory for full-size renders; never committed",
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-wait-seconds", type=float, default=600.0)
    args = parser.parse_args(argv)

    async def run() -> tuple[list[RenderResult], float | None]:
        print("checking /comfyui-hold/status before rendering...", flush=True)
        await wait_for_a_clear_hold(
            poll_seconds=args.poll_seconds,
            max_wait_seconds=args.max_wait_seconds,
            on_wait=lambda status: print(
                f"  hold open ({status}); waiting", flush=True
            ),
        )
        results: list[RenderResult] = []
        cold_start: float | None = None
        for job in plan():
            print(
                f"rendering {job.product} ({job.style}, seed={job.seed})...", flush=True
            )
            result = await render_one(job, args.full_dir)
            if result.ok and result.full_path is not None:
                write_thumbnails(result.full_path, args.image_dir, job)
                print(f"  -> {result.seconds:.1f}s", flush=True)
            else:
                print(f"  FAILED: {result.error}", flush=True)
            if cold_start is None:
                cold_start = result.seconds
            results.append(result)
        return results, cold_start

    results, cold_start = asyncio.run(run())
    markdown = render_markdown(results, args.image_dir.name, cold_start)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    ok = sum(1 for r in results if r.ok)
    print(f"{ok}/{len(results)} renders ok -> wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
