"""Q18 subjects: proposing visual subjects for the generated-icon gap, test-doubled at the
gateway. `scripts.propose_icon_subjects` is the only place that calls the LLM for this;
`app.services.icon_subjects` only ever reads the cache file it writes.
"""

from __future__ import annotations

import json

import httpx
import pytest
from scripts import propose_icon_subjects as script

from app.services.llm_extractor import LLMExtractionError


def _response(content: str, status: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "http://gateway.test/chat/completions")
    body = {"choices": [{"message": {"content": content}}]}
    return httpx.Response(status, json=body, request=request)


class TestParseSubjects:
    def test_a_usable_answer_is_kept(self) -> None:
        asked = [script.SubjectRequest(id="1", name="Quark")]
        content = json.dumps(
            {"r": [{"id": "1", "subject": "a tub of smooth white soft cheese"}]}
        )

        assert script.parse_subjects(content, asked) == {
            "Quark": "a tub of smooth white soft cheese"
        }

    def test_an_answer_for_an_id_not_asked_about_is_dropped(self) -> None:
        asked = [script.SubjectRequest(id="1", name="Quark")]
        content = json.dumps({"r": [{"id": "99", "subject": "something"}]})

        assert script.parse_subjects(content, asked) == {}

    def test_a_blank_answer_is_dropped(self) -> None:
        asked = [script.SubjectRequest(id="1", name="Quark")]
        content = json.dumps({"r": [{"id": "1", "subject": "   "}]})

        assert script.parse_subjects(content, asked) == {}

    def test_an_answer_that_still_names_the_product_is_dropped(self) -> None:
        """The whole point is to stop drawing the word; an answer that just repeats
        the name back is not a visual description."""
        asked = [script.SubjectRequest(id="1", name="Karelian pasty")]
        content = json.dumps({"r": [{"id": "1", "subject": "a Karelian pasty"}]})

        assert script.parse_subjects(content, asked) == {}

    def test_a_response_with_no_result_list_raises(self) -> None:
        asked = [script.SubjectRequest(id="1", name="Quark")]

        with pytest.raises(LLMExtractionError):
            script.parse_subjects(json.dumps({}), asked)


class TestProposeSubjects:
    async def test_it_batches_and_merges_across_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(script, "BATCH_SIZE", 1)
        calls: list[list[script.SubjectRequest]] = []

        async def fake_complete(batch: list[script.SubjectRequest]) -> str:
            calls.append(batch)
            (request,) = batch
            return json.dumps(
                {"r": [{"id": request.id, "subject": f"visual for #{request.id}"}]}
            )

        monkeypatch.setattr(script, "_complete", fake_complete)

        result = await script.propose_subjects(["Quark", "Leek"])

        assert len(calls) == 2
        assert result == {
            "Quark": "visual for #1",
            "Leek": "visual for #2",
        }

    async def test_no_names_calls_the_gateway_never(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = False

        async def fake_complete(batch):
            nonlocal called
            called = True
            return "{}"

        monkeypatch.setattr(script, "_complete", fake_complete)

        assert await script.propose_subjects([]) == {}
        assert called is False


class TestCollectNames:
    def test_names_file_lines_are_read_in_order_and_comments_skipped(
        self, tmp_path
    ) -> None:
        path = tmp_path / "names.txt"
        path.write_text("Quark\n# a comment\n\nLeek\n", encoding="utf-8")

        assert script._collect_names([], path) == ["Quark", "Leek"]

    def test_names_and_names_file_are_combined_and_deduplicated(self, tmp_path) -> None:
        path = tmp_path / "names.txt"
        path.write_text("leek\nMustard\n", encoding="utf-8")

        assert script._collect_names(["Quark", "Leek"], path) == [
            "Quark",
            "Leek",
            "Mustard",
        ]


class TestSkipBriefed:
    def test_a_product_with_an_operator_brief_is_skipped(self, capsys) -> None:
        result = script._skip_briefed(["Quark", "Tomato puree"])

        assert result == ["Quark"]
        assert "skipping 1" in capsys.readouterr().out


class TestApply:
    def test_a_draft_merges_into_a_fresh_cache(self, tmp_path) -> None:
        draft = tmp_path / "draft.json"
        cache = tmp_path / "cache.json"
        draft.write_text(
            json.dumps({"Quark": "a tub of soft cheese"}), encoding="utf-8"
        )

        assert script._apply(draft, cache) == 0

        assert json.loads(cache.read_text(encoding="utf-8")) == {
            "Quark": "a tub of soft cheese"
        }

    def test_a_draft_merges_into_an_existing_cache_without_dropping_other_entries(
        self, tmp_path
    ) -> None:
        draft = tmp_path / "draft.json"
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"Leek": "a bundle of leeks"}), encoding="utf-8")
        draft.write_text(
            json.dumps({"Quark": "a tub of soft cheese"}), encoding="utf-8"
        )

        script._apply(draft, cache)

        assert json.loads(cache.read_text(encoding="utf-8")) == {
            "Leek": "a bundle of leeks",
            "Quark": "a tub of soft cheese",
        }

    def test_a_draft_entry_overwrites_an_existing_one_of_the_same_name(
        self, tmp_path
    ) -> None:
        draft = tmp_path / "draft.json"
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"Quark": "stale text"}), encoding="utf-8")
        draft.write_text(json.dumps({"Quark": "fresh text"}), encoding="utf-8")

        script._apply(draft, cache)

        assert json.loads(cache.read_text(encoding="utf-8")) == {"Quark": "fresh text"}

    def test_a_non_object_draft_is_refused(self, tmp_path, capsys) -> None:
        draft = tmp_path / "draft.json"
        cache = tmp_path / "cache.json"
        draft.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        assert script._apply(draft, cache) == 1
        assert not cache.exists()


class TestMain:
    def test_no_names_given_does_nothing(self, capsys) -> None:
        assert script.main([]) == 0
        assert "nothing to propose" in capsys.readouterr().out

    def test_dry_run_prints_and_writes_nothing(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        async def fake_propose(names: list[str]) -> dict[str, str]:
            return {name: f"a photo of {name.lower()}" for name in names}

        monkeypatch.setattr(script, "propose_subjects", fake_propose)
        out_path = tmp_path / "draft.json"

        result = script.main(["--names", "Leek", "--dry-run", "--out", str(out_path)])

        assert result == 0
        assert "a photo of leek" in capsys.readouterr().out
        assert not out_path.exists()

    def test_a_plain_run_writes_the_draft_not_the_cache(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_propose(names: list[str]) -> dict[str, str]:
            return {name: f"a photo of {name.lower()}" for name in names}

        monkeypatch.setattr(script, "propose_subjects", fake_propose)
        out_path = tmp_path / "draft.json"
        cache_path = tmp_path / "cache.json"

        result = script.main(
            [
                "--names",
                "Leek",
                "--out",
                str(out_path),
                "--cache",
                str(cache_path),
            ]
        )

        assert result == 0
        assert json.loads(out_path.read_text(encoding="utf-8")) == {
            "Leek": "a photo of leek"
        }
        assert not cache_path.exists()

    def test_a_product_with_a_brief_is_never_sent_to_the_gateway(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_propose(names: list[str]) -> dict[str, str]:
            assert "Tomato puree" not in names
            return {}

        monkeypatch.setattr(script, "propose_subjects", fake_propose)

        assert script.main(["--names", "Tomato puree", "--dry-run"]) == 0

    def test_apply_merges_without_calling_the_gateway(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_propose(names: list[str]) -> dict[str, str]:
            raise AssertionError("the gateway must not be called on --apply")

        monkeypatch.setattr(script, "propose_subjects", fake_propose)
        draft = tmp_path / "draft.json"
        cache = tmp_path / "cache.json"
        draft.write_text(
            json.dumps({"Quark": "a tub of soft cheese"}), encoding="utf-8"
        )

        assert script.main(["--apply", str(draft), "--cache", str(cache)]) == 0
        assert json.loads(cache.read_text(encoding="utf-8")) == {
            "Quark": "a tub of soft cheese"
        }
