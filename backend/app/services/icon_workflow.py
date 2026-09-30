"""Q18-G1: the frozen ComfyUI icon-generation graph.

This is the one place the graph shape lives. The client (`app/services/comfyui.py`) only
ever submits whatever `build_icon_workflow` returns; nothing else builds or edits a
ComfyUI prompt. See `docs/spikes/Q18_icon_styles.md` for where the graph came from and how
the two LoRA styles compare.

The LoRA (`SDXL-Emoji-Lora-r4.safetensors`) has two trigger words that are mutually
exclusive - never both in the same prompt - and each only looks right within its own
strength range:
- ``emoji``: the 3D emoji look, strength 0.2 to 0.5.
- ``flat``: the flat icon look, strength 0.7 to 0.8.
"""

from __future__ import annotations

from typing import Any, Literal

Style = Literal["emoji", "flat"]

CHECKPOINT = "sd_xl_base_1.0.safetensors"
LORA_NAME = "SDXL-Emoji-Lora-r4.safetensors"
NEGATIVE_PROMPT = "blurry, text, watermark"
BIREFNET_MODEL = "General.safetensors"

# Canvas and batch are fixed; the spec forbids passing them in (1024x1024 peaks the card,
# and batch_size 1 is the only size measured).
CANVAS_SIZE = 1024
BATCH_SIZE = 1

TRIGGERS: dict[Style, str] = {"emoji": "emoji", "flat": "flat"}
DEFAULT_LORA_STRENGTH: dict[Style, float] = {"emoji": 0.35, "flat": 0.75}
LORA_STRENGTH_RANGE: dict[Style, tuple[float, float]] = {
    "emoji": (0.2, 0.5),
    "flat": (0.7, 0.8),
}


def build_icon_workflow(
    subject: str,
    *,
    style: Style,
    seed: int,
    reference_image: str | None = None,
    steps: int = 25,
    lora_strength: float | None = None,
) -> dict[str, Any]:
    """The verified icon graph for one product.

    ``subject`` is the product's generic name plus the operator's icon brief where there
    is one, e.g. "Tomato puree, a small can or squeeze out tube". ``lora_strength``
    defaults per style (0.35 for emoji, 0.75 for flat) and is checked against that style's
    allowed range when given explicitly. Without ``reference_image``, the IP-Adapter nodes
    (9, 10, 11) are left out and KSampler samples straight off the LoRA-loaded model
    (node 2), which saves ~2 GB of VRAM.
    """
    if style not in TRIGGERS:
        raise ValueError(f"style must be 'emoji' or 'flat', got {style!r}")

    strength = DEFAULT_LORA_STRENGTH[style] if lora_strength is None else lora_strength
    low, high = LORA_STRENGTH_RANGE[style]
    if not low <= strength <= high:
        raise ValueError(
            f"{style} LoRA strength must be between {low} and {high}, got {strength}"
        )

    # The flat form swaps the trigger word and must never say "emoji".
    positive_text = f"{TRIGGERS[style]}, {subject}, simple flat icon, white background"

    graph: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": CHECKPOINT},
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "lora_name": LORA_NAME,
                "strength_model": strength,
                "strength_clip": strength,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 1], "text": positive_text},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 1], "text": NEGATIVE_PROMPT},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": CANVAS_SIZE,
                "height": CANVAS_SIZE,
                "batch_size": BATCH_SIZE,
            },
        },
    }

    if reference_image is None:
        sampler_model = ["2", 0]
    else:
        graph["9"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": ["2", 0], "preset": "PLUS (high strength)"},
        }
        graph["10"] = {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image},
        }
        graph["11"] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["9", 0],
                "ipadapter": ["9", 1],
                "image": ["10", 0],
                "weight": 0.6,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 1.0,
                "embeds_scaling": "V only",
            },
        }
        sampler_model = ["11", 0]

    graph["6"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": sampler_model,
            "positive": ["3", 0],
            "negative": ["4", 0],
            "latent_image": ["5", 0],
            "seed": seed,
            "steps": steps,
            "cfg": 7.0,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 1.0,
        },
    }
    graph["7"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
    }
    graph["12"] = {
        "class_type": "LoadRembgByBiRefNetModel",
        "inputs": {"model": BIREFNET_MODEL, "device": "AUTO"},
    }
    graph["13"] = {
        "class_type": "RembgByBiRefNet",
        "inputs": {"model": ["12", 0], "images": ["7", 0]},
    }
    graph["8"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["13", 0], "filename_prefix": "product_icon"},
    }

    return graph
