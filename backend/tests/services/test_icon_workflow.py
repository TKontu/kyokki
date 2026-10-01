"""Q18-G1: the frozen ComfyUI icon workflow template."""

from __future__ import annotations

import pytest

from app.services.icon_workflow import build_icon_workflow


class TestGraphShape:
    def test_graph_matches_the_verified_shape_without_a_reference(self) -> None:
        graph = build_icon_workflow("Tomato puree", style="emoji", seed=42)

        assert set(graph.keys()) == {"1", "2", "3", "4", "5", "6", "7", "8", "12", "13"}
        assert graph["1"] == {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        }
        assert graph["2"]["class_type"] == "LoraLoader"
        assert graph["2"]["inputs"]["lora_name"] == "SDXL-Emoji-Lora-r4.safetensors"
        assert graph["2"]["inputs"]["model"] == ["1", 0]
        assert graph["2"]["inputs"]["clip"] == ["1", 1]
        assert graph["6"]["class_type"] == "KSampler"
        # No reference image: KSampler must be rewired straight to the LoRA-loaded model.
        assert graph["6"]["inputs"]["model"] == ["2", 0]
        assert graph["7"] == {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        }
        assert graph["12"] == {
            "class_type": "LoadRembgByBiRefNetModel",
            "inputs": {"model": "General.safetensors", "device": "AUTO"},
        }
        assert graph["13"] == {
            "class_type": "RembgByBiRefNet",
            "inputs": {"model": ["12", 0], "images": ["7", 0]},
        }
        assert graph["8"] == {
            "class_type": "SaveImage",
            "inputs": {"images": ["13", 0], "filename_prefix": "product_icon"},
        }

    def test_reference_image_adds_the_ip_adapter_nodes(self) -> None:
        graph = build_icon_workflow(
            "Canned tuna",
            style="emoji",
            seed=1,
            reference_image="ref.png",
        )

        assert set(graph.keys()) == {
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "10",
            "11",
            "12",
            "13",
        }
        assert graph["9"] == {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": ["2", 0], "preset": "PLUS (high strength)"},
        }
        assert graph["10"] == {
            "class_type": "LoadImage",
            "inputs": {"image": "ref.png"},
        }
        assert graph["11"]["class_type"] == "IPAdapterAdvanced"
        assert graph["11"]["inputs"]["model"] == ["9", 0]
        assert graph["11"]["inputs"]["ipadapter"] == ["9", 1]
        assert graph["11"]["inputs"]["image"] == ["10", 0]
        # With a reference image, KSampler must sample off the IP-Adapter node.
        assert graph["6"]["inputs"]["model"] == ["11", 0]

    def test_canvas_and_batch_are_fixed_and_cannot_be_overridden(self) -> None:
        graph = build_icon_workflow("Parsnip", style="flat", seed=7)

        assert graph["5"]["inputs"] == {
            "width": 1024,
            "height": 1024,
            "batch_size": 1,
        }
        # There is no width/height/batch_size parameter to pass in.
        with pytest.raises(TypeError):
            build_icon_workflow(  # type: ignore[call-arg]
                "Parsnip", style="flat", seed=7, batch_size=4
            )

    def test_steps_and_seed_flow_into_the_sampler(self) -> None:
        graph = build_icon_workflow("Quark", style="emoji", seed=12345, steps=40)

        assert graph["6"]["inputs"]["seed"] == 12345
        assert graph["6"]["inputs"]["steps"] == 40

    @pytest.mark.parametrize("seed", [0, 1, 2**64 - 1])
    def test_seed_at_the_edges_of_the_valid_range_is_accepted(self, seed: int) -> None:
        graph = build_icon_workflow("Leek", style="flat", seed=seed)
        assert graph["6"]["inputs"]["seed"] == seed

    @pytest.mark.parametrize("seed", [-1, 2**64])
    def test_seed_outside_0_to_2_64_minus_1_is_rejected(self, seed: int) -> None:
        with pytest.raises(ValueError):
            build_icon_workflow("Leek", style="flat", seed=seed)


class TestStyles:
    def test_emoji_style_uses_the_emoji_trigger_and_default_strength(self) -> None:
        graph = build_icon_workflow("Mozzarella", style="emoji", seed=1)

        assert graph["3"]["inputs"]["text"].startswith("emoji, Mozzarella,")
        assert graph["2"]["inputs"]["strength_model"] == 0.35
        assert graph["2"]["inputs"]["strength_clip"] == 0.35

    def test_flat_style_uses_the_flat_trigger_and_default_strength_and_says_no_emoji(
        self,
    ) -> None:
        graph = build_icon_workflow("Mozzarella", style="flat", seed=1)

        assert graph["3"]["inputs"]["text"].startswith("flat, Mozzarella,")
        assert "emoji" not in graph["3"]["inputs"]["text"]
        assert graph["2"]["inputs"]["strength_model"] == 0.75
        assert graph["2"]["inputs"]["strength_clip"] == 0.75

    def test_negative_prompt_is_always_the_same(self) -> None:
        expected = build_icon_workflow("Oat drink", style="emoji", seed=1)["4"][
            "inputs"
        ]["text"]
        for style in ("emoji", "flat"):
            graph = build_icon_workflow("Oat drink", style=style, seed=1)  # type: ignore[arg-type]
            assert graph["4"]["inputs"]["text"] == expected

    def test_negative_prompt_excludes_faces_in_both_styles(self) -> None:
        """Operator ruling (2026-09-30): 'Flat. No faces'"""
        face_terms = (
            "face",
            "eyes",
            "mouth",
            "smile",
            "cartoon character",
            "mascot",
            "anthropomorphic",
        )
        for style in ("emoji", "flat"):
            negative = build_icon_workflow("Oat drink", style=style, seed=1)["4"][  # type: ignore[arg-type]
                "inputs"
            ]["text"]
            assert negative.startswith("blurry, text, watermark")
            for term in face_terms:
                assert term in negative, (
                    f"{term!r} missing from negative prompt: {negative!r}"
                )

    def test_default_style_is_flat(self) -> None:
        """Operator ruling (2026-09-30): 'Flat. No faces'"""
        graph = build_icon_workflow("Leek", seed=1)
        assert graph["3"]["inputs"]["text"].startswith("flat,")
        assert graph["2"]["inputs"]["strength_model"] == 0.75
        assert graph["2"]["inputs"]["strength_clip"] == 0.75

    def test_emoji_style_is_still_available_explicitly(self) -> None:
        graph = build_icon_workflow("Leek", style="emoji", seed=1)
        assert graph["3"]["inputs"]["text"].startswith("emoji,")
        assert graph["2"]["inputs"]["strength_model"] == 0.35

    def test_flat_positive_prompt_asks_for_nothing_character_like(self) -> None:
        text = build_icon_workflow("Leek", style="flat", seed=1)["3"]["inputs"][
            "text"
        ].lower()
        for term in (
            "face",
            "character",
            "mascot",
            "cute",
            "smile",
            "eyes",
            "anthropomorphic",
        ):
            assert term not in text

    def test_the_two_triggers_never_both_appear_in_one_prompt(self) -> None:
        emoji_text = build_icon_workflow("Leek", style="emoji", seed=1)["3"]["inputs"][
            "text"
        ]
        flat_text = build_icon_workflow("Leek", style="flat", seed=1)["3"]["inputs"][
            "text"
        ]
        assert "flat" not in emoji_text.split(",")[0]
        assert "emoji" not in flat_text

    def test_unknown_style_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_icon_workflow("Leek", style="cartoon", seed=1)  # type: ignore[arg-type]

    @pytest.mark.parametrize("strength", [0.2, 0.35, 0.5])
    def test_emoji_strength_can_be_overridden_within_range(
        self, strength: float
    ) -> None:
        graph = build_icon_workflow(
            "Leek", style="emoji", seed=1, lora_strength=strength
        )
        assert graph["2"]["inputs"]["strength_model"] == strength

    @pytest.mark.parametrize("strength", [0.1, 0.19, 0.51, 0.8])
    def test_emoji_strength_out_of_range_is_rejected(self, strength: float) -> None:
        with pytest.raises(ValueError):
            build_icon_workflow("Leek", style="emoji", seed=1, lora_strength=strength)

    @pytest.mark.parametrize("strength", [0.7, 0.75, 0.8])
    def test_flat_strength_can_be_overridden_within_range(
        self, strength: float
    ) -> None:
        graph = build_icon_workflow(
            "Leek", style="flat", seed=1, lora_strength=strength
        )
        assert graph["2"]["inputs"]["strength_model"] == strength

    @pytest.mark.parametrize("strength", [0.35, 0.69, 0.81, 1.0])
    def test_flat_strength_out_of_range_is_rejected(self, strength: float) -> None:
        with pytest.raises(ValueError):
            build_icon_workflow("Leek", style="flat", seed=1, lora_strength=strength)
