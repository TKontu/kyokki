"""Q18-G1 style trial script: the product list, the hold wait, rendering and the write-up.

Everything here stubs `app.services.comfyui`; no test reaches the network or the GPU host.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from scripts import icon_style_trial
from scripts.icon_style_trial import Job, RenderResult


def _fake_png(size: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (size, size), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


class TestProductsAndPlan:
    def test_the_ten_named_products_are_all_present(self) -> None:
        names = {name for name, _brief in icon_style_trial.PRODUCTS}
        assert names == {
            "Tomato puree",
            "Canned tuna",
            "Fish fingers",
            "Canned tomatoes",
            "Quark",
            "Mozzarella",
            "Minced beef",
            "Parsnip",
            "Karelian pasty",
            "Oat drink",
        }
        assert len(icon_style_trial.PRODUCTS) == 10

    def test_plan_is_ten_products_by_two_styles_by_two_seeds(self) -> None:
        jobs = icon_style_trial.plan()
        assert len(jobs) == 40
        assert {j.style for j in jobs} == {"emoji", "flat"}
        assert {j.seed for j in jobs} == set(icon_style_trial.SEEDS)
        assert len(icon_style_trial.SEEDS) == 2

    def test_build_subject_appends_the_brief_when_there_is_one(self) -> None:
        assert (
            icon_style_trial.build_subject("Tomato puree", "a small can or tube")
            == "Tomato puree, a small can or tube"
        )
        assert icon_style_trial.build_subject("Quark", None) == "Quark"

    def test_slug_is_filesystem_safe(self) -> None:
        assert icon_style_trial.slug("Tomato puree") == "tomato_puree"
        assert "/" not in icon_style_trial.slug("A/B, C")


class TestWaitForAClearHold:
    async def test_proceeds_immediately_when_the_hold_is_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_hold_status() -> dict[str, Any]:
            return {"open": False}

        monkeypatch.setattr(icon_style_trial.comfyui, "hold_status", fake_hold_status)
        await icon_style_trial.wait_for_a_clear_hold()  # must not raise or hang

    async def test_waits_then_proceeds_once_it_clears(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        responses = [
            {"open": True, "tasks": 1},
            {"open": True, "tasks": 1},
            {"open": False},
        ]

        async def fake_hold_status() -> dict[str, Any]:
            return responses.pop(0)

        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(icon_style_trial.comfyui, "hold_status", fake_hold_status)
        await icon_style_trial.wait_for_a_clear_hold(poll_seconds=3.0, sleep=fake_sleep)
        assert sleeps == [3.0, 3.0]

    async def test_gives_up_after_max_wait(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_hold_status() -> dict[str, Any]:
            return {"open": True, "tasks": 1}

        async def fake_sleep(seconds: float) -> None:
            return None

        monkeypatch.setattr(icon_style_trial.comfyui, "hold_status", fake_hold_status)
        with pytest.raises(TimeoutError):
            await icon_style_trial.wait_for_a_clear_hold(
                poll_seconds=5.0, max_wait_seconds=10.0, sleep=fake_sleep
            )


class TestRenderOne:
    async def test_success_writes_the_full_size_png(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        png = _fake_png()

        async def fake_render(workflow: dict[str, Any]) -> list[bytes]:
            assert workflow["3"]["inputs"]["text"].startswith("emoji, Quark")
            return [png]

        monkeypatch.setattr(icon_style_trial.comfyui, "render", fake_render)
        job = Job("Quark", None, "emoji", 111)
        result = await icon_style_trial.render_one(job, tmp_path)

        assert result.ok
        assert result.full_path is not None
        assert result.full_path.read_bytes() == png
        assert result.lora_strength == 0.35
        assert result.error is None

    async def test_comfyui_error_is_recorded_not_raised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        async def fake_render(workflow: dict[str, Any]) -> list[bytes]:
            raise icon_style_trial.comfyui.ComfyUITimeout("took too long")

        monkeypatch.setattr(icon_style_trial.comfyui, "render", fake_render)
        job = Job("Parsnip", None, "flat", 222)
        result = await icon_style_trial.render_one(job, tmp_path)

        assert not result.ok
        assert result.full_path is None
        assert "took too long" in (result.error or "")

    async def test_no_images_is_a_recorded_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        async def fake_render(workflow: dict[str, Any]) -> list[bytes]:
            return []

        monkeypatch.setattr(icon_style_trial.comfyui, "render", fake_render)
        job = Job("Oat drink", None, "emoji", 333)
        result = await icon_style_trial.render_one(job, tmp_path)

        assert not result.ok
        assert result.error == "no images returned"


class TestThumbnails:
    def test_writes_256_and_64_px_copies(self, tmp_path: Path) -> None:
        full_path = tmp_path / "full.png"
        full_path.write_bytes(_fake_png(512))
        image_dir = tmp_path / "images"
        job = Job("Mozzarella", None, "flat", 42)

        written = icon_style_trial.write_thumbnails(full_path, image_dir, job)

        assert set(written) == {256, 64}
        with Image.open(written[256]) as img:
            assert img.size == (256, 256)
        with Image.open(written[64]) as img:
            assert img.size == (64, 64)
        for path in written.values():
            assert path.stat().st_size > 0

    def test_thumbnail_total_size_is_small(self, tmp_path: Path) -> None:
        """A sanity check for the doc's 3 MB budget: tiny tile-sized PNGs stay tiny."""
        full_path = tmp_path / "full.png"
        full_path.write_bytes(_fake_png(1024))
        image_dir = tmp_path / "images"
        job = Job("Minced beef", None, "emoji", 7)

        written = icon_style_trial.write_thumbnails(full_path, image_dir, job)

        total = sum(p.stat().st_size for p in written.values())
        assert (
            total < 50_000
        )  # a single flat-colour test PNG; real renders still fit 3MB/80


class TestMarkdown:
    def _result(
        self, product: str, style: str, seed: int, ok: bool = True
    ) -> RenderResult:
        job = Job(product, None, style, seed)  # type: ignore[arg-type]
        if ok:
            return RenderResult(job, 0.35, 21.3, Path(f"{product}.png"))
        return RenderResult(job, 0.35, 5.0, None, error="boom")

    def test_markdown_has_a_table_per_product_and_a_failures_section(self) -> None:
        results = [
            self._result("Quark", "emoji", 1),
            self._result("Quark", "emoji", 2),
            self._result("Quark", "flat", 1),
            self._result("Quark", "flat", 2, ok=False),
        ]
        markdown = icon_style_trial.render_markdown(results, "q18_icon_styles", 34.2)

        assert "### Quark" in markdown
        assert "seed 20260930" in markdown or "seed 1" in markdown
        assert "## Failures (1)" in markdown
        assert "boom" in markdown
        assert "34.2s" in markdown
        assert "## Next round" in markdown
        assert "## Reading the styles" in markdown
        assert "## Recommended LoRA strength" in markdown

    def test_no_failures_section_says_none(self) -> None:
        results = [self._result("Quark", "emoji", 1)]
        markdown = icon_style_trial.render_markdown(results, "q18_icon_styles", None)
        assert "## Failures (0)" in markdown
        assert "None." in markdown


class TestRegeneratingKeepsTheRulingAndRecheck:
    """review verdict #7: re-running the script must not silently drop the operator
    ruling or the flat-recheck section from the committed doc."""

    def test_render_markdown_always_includes_the_operator_ruling(self) -> None:
        markdown = icon_style_trial.render_markdown([], "q18_icon_styles", None)
        assert "## Operator ruling" in markdown
        assert "Flat. No faces" in markdown
        assert "Flat. No faces." not in markdown  # no full stop inside the quote

    def test_render_markdown_always_includes_the_flat_recheck_section(self) -> None:
        markdown = icon_style_trial.render_markdown([], "q18_icon_styles", None)
        assert "Flat, no faces (recheck" in markdown
        for name, _brief in icon_style_trial.PRODUCTS:
            slug = icon_style_trial.slug(name)
            assert slug in markdown
            assert f"{slug}_flat_{icon_style_trial.RECHECK_SEED}_256.png" in markdown
            assert f"{slug}_flat_{icon_style_trial.RECHECK_SEED}_64.png" in markdown

    def test_graph_method_matches_the_current_negative_prompt(self) -> None:
        from app.services.icon_workflow import NEGATIVE_PROMPT

        assert NEGATIVE_PROMPT in icon_style_trial.GRAPH_METHOD
