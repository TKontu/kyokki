"""Q18 exact-emoji trial: the picker script, with the model stubbed."""

from __future__ import annotations

import csv
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from scripts import emoji_trial
from scripts.emoji_trial import Product, Result

REFERENCE = [
    {"e": "🥦", "name": "broccoli", "version": "5.0", "subgroup": "food-vegetable"},
    {"e": "🍇", "name": "grapes", "version": "0.6", "subgroup": "food-fruit"},
    {"e": "🍞", "name": "bread", "version": "0.6", "subgroup": "food-prepared"},
    {"e": "🥩", "name": "cut of meat", "version": "1.0", "subgroup": "food-prepared"},
    {"e": "🕯️", "name": "candle", "version": "0.7", "subgroup": "light & video"},
]


def _answer(rows: list[dict[str, Any]]) -> str:
    return json.dumps({"r": rows}, ensure_ascii=False)


class TestBuildReference:
    EMOJI_TEST = """# emoji-test.txt
# Version: 18.0

# group: Animals & Nature

# subgroup: animal-mammal
1F404                                                  ; fully-qualified     # 🐄 E1.0 cow

# subgroup: plant-other
1F33F                                                  ; fully-qualified     # 🌿 E0.6 herb

# group: Food & Drink

# subgroup: food-vegetable
1F966                                                  ; fully-qualified     # 🥦 E5.0 broccoli
1FADC                                                  ; fully-qualified     # 🫜 E16.0 root vegetable

# subgroup: food-fruit
1F34B 200D 1F7E9                                       ; fully-qualified     # 🍋‍🟩 E15.1 lime

# group: Objects

# subgroup: light & video
1F56F FE0F                                             ; fully-qualified     # 🕯️ E0.7 candle
1F56F                                                  ; unqualified         # 🕯 E0.7 candle

# subgroup: household
1F9FC                                                  ; fully-qualified     # 🧼 E11.0 soap
1FA91                                                  ; fully-qualified     # 🪑 E12.0 chair
"""

    def test_it_keeps_food_plants_and_named_household_objects(self) -> None:
        data = emoji_trial.build_reference(self.EMOJI_TEST, cutoff="15.1")

        names = [entry["name"] for entry in data["emoji"]]
        assert names == ["herb", "broccoli", "lime", "candle", "soap"]
        assert data["unicode_emoji_version"] == "18.0"
        assert data["cutoff"] == "15.1"

    def test_it_uses_the_fully_qualified_form(self) -> None:
        data = emoji_trial.build_reference(self.EMOJI_TEST, cutoff="15.1")

        candle = next(e for e in data["emoji"] if e["name"] == "candle")
        assert candle["e"] == "\U0001f56f️"

    def test_it_lists_what_the_cutoff_excluded(self) -> None:
        data = emoji_trial.build_reference(self.EMOJI_TEST, cutoff="15.1")

        assert [e["name"] for e in data["excluded_newer"]] == ["root vegetable"]
        assert "root vegetable" not in [e["name"] for e in data["emoji"]]

    def test_the_shipped_reference_is_within_its_cutoff(self) -> None:
        data = emoji_trial.load_reference_file()

        cutoff = emoji_trial.version_key(data["cutoff"])
        assert data["emoji"], "the reference list is empty"
        for entry in data["emoji"]:
            assert emoji_trial.version_key(entry["version"]) <= cutoff, entry
        by_name = {e["name"]: e["e"] for e in data["emoji"]}
        for name in ("broccoli", "grapes", "egg", "cookie", "butter", "glass of milk"):
            assert name in by_name, name
        for name in ("soap", "roll of paper", "sponge", "toothbrush", "candle", "pill"):
            assert name in by_name, name
        # Emoji 18.0 files the seafood under Animals & Nature, not Food & Drink.
        for name in ("shrimp", "squid", "oyster", "crab", "lobster", "fish"):
            assert name in by_name, name


class TestReadNames:
    def test_it_reads_name_and_category_columns(self, tmp_path: Path) -> None:
        path = tmp_path / "names.csv"
        path.write_text(
            "name,category\nBroccoli,produce\nRye bread,bread\n", encoding="utf-8"
        )

        assert emoji_trial.read_names(path) == [
            Product("Broccoli", "produce"),
            Product("Rye bread", "bread"),
        ]

    def test_a_bare_name_list_works_and_blank_lines_and_duplicates_go(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "names.txt"
        path.write_text("Broccoli\n\nGrapes\nbroccoli\n", encoding="utf-8")

        assert emoji_trial.read_names(path) == [
            Product("Broccoli", None),
            Product("Grapes", None),
        ]

    def test_a_bare_header_line_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "names.txt"
        path.write_text("name\nBroccoli\n", encoding="utf-8")

        assert emoji_trial.read_names(path) == [Product("Broccoli", None)]

    def test_duplicate_names_are_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = tmp_path / "names.csv"
        path.write_text("Rye bread,bread\nrye bread,snacks\n", encoding="utf-8")

        assert emoji_trial.read_names(path) == [Product("Rye bread", "bread")]
        assert "rye bread" in capsys.readouterr().out.lower()


class TestFromDb:
    async def test_it_reads_names_and_categories_read_only(self) -> None:
        executed: list[str] = []

        class FakeResult:
            def all(self) -> list[tuple[str, str]]:
                return [("Broccoli", "produce"), ("Entrecôte", "meat")]

        class FakeSession:
            async def execute(self, statement: Any) -> FakeResult:
                executed.append(str(statement))
                return FakeResult()

        @asynccontextmanager
        async def sessions():  # type: ignore[no-untyped-def]
            yield FakeSession()

        products = await emoji_trial.load_from_db(sessions)

        assert products == [
            Product("Broccoli", "produce"),
            Product("Entrecôte", "meat"),
        ]
        assert "READ ONLY" in executed[0].upper()
        assert "product_master" in executed[1]
        assert "canonical_name" in executed[1]

    async def test_a_limit_caps_the_query(self) -> None:
        executed: list[tuple[str, Any]] = []

        class FakeResult:
            def all(self) -> list[tuple[str, str]]:
                return []

        class FakeSession:
            async def execute(self, statement: Any, params: Any = None) -> FakeResult:
                executed.append((str(statement), params))
                return FakeResult()

        @asynccontextmanager
        async def sessions():  # type: ignore[no-untyped-def]
            yield FakeSession()

        await emoji_trial.load_from_db(sessions, limit=5)

        assert "LIMIT" in executed[1][0].upper()
        assert executed[1][1] == {"limit": 5}

    def test_the_default_sessions_come_from_the_app(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.db.session as app_session

        sentinel = object()
        monkeypatch.setattr(app_session, "AsyncSessionLocal", lambda: sentinel)

        assert emoji_trial._default_sessions() is sentinel

    async def test_dispose_engine_disposes_the_app_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.db.session as app_session

        disposed: list[bool] = []

        class FakeEngine:
            async def dispose(self) -> None:
                disposed.append(True)

        monkeypatch.setattr(app_session, "engine", FakeEngine())

        await emoji_trial._dispose_engine()

        assert disposed == [True]


class TestPrompt:
    def test_it_lists_the_emoji_the_rule_and_the_products(self) -> None:
        prompt = emoji_trial.build_prompt(
            [Product("Broccoli", "produce"), Product("Parsnip", None)], REFERENCE
        )

        assert "🥦 broccoli" in prompt
        assert "🥩 cut of meat" in prompt
        assert "1. Broccoli (category: produce)" in prompt
        assert "2. Parsnip" in prompt
        assert "closest" in prompt.lower()

    def test_the_payload_has_a_strict_schema_and_the_reasoning_strength(self) -> None:
        payload = emoji_trial.build_payload(
            "prompt", model="c2.muse-glimmer", reasoning="low", max_tokens=4096
        )

        assert payload["model"] == "c2.muse-glimmer"
        assert payload["chat_template_kwargs"] == {"reasoning_strength": "low"}
        schema = payload["response_format"]["json_schema"]
        assert schema["strict"] is True
        row = schema["schema"]["properties"]["r"]["items"]
        assert set(row["required"]) == {"i", "e", "m", "why"}
        assert row["properties"]["m"]["enum"] == ["exact", "borderline", "none"]

    def test_no_reasoning_strength_leaves_the_kwarg_out(self) -> None:
        payload = emoji_trial.build_payload(
            "prompt", model="m", reasoning=None, max_tokens=10
        )

        assert "chat_template_kwargs" not in payload


class TestParseAnswers:
    BATCH = [
        Product("Broccoli", "produce"),
        Product("Parsnip", "produce"),
        Product("Entrecôte", "meat"),
    ]

    def test_it_maps_answers_back_to_products(self) -> None:
        text = _answer(
            [
                {"i": 1, "e": "🥦", "m": "exact", "why": "broccoli"},
                {"i": 2, "e": None, "m": "none", "why": "carrot is not parsnip"},
                {"i": 3, "e": "🥩", "m": "borderline", "why": "generic meat"},
            ]
        )

        results = emoji_trial.parse_answers(text, self.BATCH, REFERENCE)

        assert results == [
            Result("Broccoli", "produce", "🥦", "exact", "broccoli"),
            Result("Parsnip", "produce", None, "none", "carrot is not parsnip"),
            Result("Entrecôte", "meat", "🥩", "borderline", "generic meat"),
        ]

    def test_an_emoji_outside_the_list_is_invalid(self) -> None:
        text = _answer([{"i": 1, "e": "🥕", "m": "exact", "why": "close enough"}])

        (result,) = emoji_trial.parse_answers(text, self.BATCH[1:2], REFERENCE)

        assert result.match == "invalid"
        assert result.emoji is None
        assert "🥕" in result.why

    def test_exact_without_an_emoji_is_invalid(self) -> None:
        text = _answer([{"i": 1, "e": None, "m": "exact", "why": "?"}])

        (result,) = emoji_trial.parse_answers(text, self.BATCH[:1], REFERENCE)

        assert result.match == "invalid"

    def test_none_never_keeps_a_closest_emoji(self) -> None:
        text = _answer([{"i": 1, "e": "🍞", "m": "none", "why": "rye is not bread"}])

        (result,) = emoji_trial.parse_answers(
            text, [Product("Rye bread", "bread")], REFERENCE
        )

        assert result == Result("Rye bread", "bread", None, "none", "rye is not bread")

    def test_a_missing_variation_selector_still_matches(self) -> None:
        text = _answer([{"i": 1, "e": "\U0001f56f", "m": "exact", "why": "candle"}])

        (result,) = emoji_trial.parse_answers(
            text, [Product("Candles", None)], REFERENCE
        )

        assert result.emoji == "\U0001f56f️"
        assert result.match == "exact"

    def test_a_partial_answer_rejects_the_whole_batch(self) -> None:
        """Numbering must be exactly 1..n: a gap means the rows cannot be trusted."""
        text = _answer([{"i": 1, "e": "🥦", "m": "exact", "why": "broccoli"}])

        results = emoji_trial.parse_answers(text, self.BATCH[:2], REFERENCE)

        assert [r.match for r in results] == ["invalid", "invalid"]
        assert all(r.emoji is None for r in results)
        assert "1..2" in results[0].why

    def test_zero_based_numbering_rejects_the_batch(self) -> None:
        """Review: 0-based answers shifted onto other products (Parsnip -> grapes, exact)."""
        text = _answer(
            [
                {"i": 0, "e": "🥦", "m": "exact", "why": "broccoli"},
                {"i": 1, "e": "🍇", "m": "exact", "why": "grapes"},
                {"i": 2, "e": None, "m": "none", "why": "x"},
            ]
        )

        results = emoji_trial.parse_answers(text, self.BATCH, REFERENCE)

        assert {r.match for r in results} == {"invalid"}
        assert all(r.emoji is None for r in results)

    def test_a_duplicate_index_rejects_the_batch(self) -> None:
        text = _answer(
            [
                {"i": 1, "e": "🥦", "m": "exact", "why": "a"},
                {"i": 1, "e": None, "m": "none", "why": "b"},
            ]
        )

        results = emoji_trial.parse_answers(text, self.BATCH[:2], REFERENCE)

        assert {r.match for r in results} == {"invalid"}

    def test_text_that_is_not_json_makes_every_product_missing(self) -> None:
        results = emoji_trial.parse_answers("I think broccoli", self.BATCH, REFERENCE)

        assert {r.match for r in results} == {"missing"}

    def test_a_json_answer_after_reasoning_text_is_found(self) -> None:
        text = "Thinking {not json} ... " + _answer(
            [{"i": 1, "e": "🥦", "m": "exact", "why": "broccoli"}]
        )

        (result,) = emoji_trial.parse_answers(text, self.BATCH[:1], REFERENCE)

        assert result.match == "exact"


class TestRun:
    def test_it_batches_one_request_at_a_time_and_counts(self) -> None:
        products = [Product(f"P{n}", None) for n in range(5)]
        calls: list[int] = []

        def complete(batch: list[Product]) -> str:
            calls.append(len(batch))
            return _answer(
                [
                    {"i": i + 1, "e": None, "m": "none", "why": "x"}
                    for i in range(len(batch))
                ]
            )

        results = emoji_trial.run(products, REFERENCE, complete, batch_size=2)

        assert calls == [2, 2, 1]
        assert [r.name for r in results] == [p.name for p in products]
        assert emoji_trial.count(results) == {
            "exact": 0,
            "borderline": 0,
            "none": 5,
            "invalid": 0,
            "missing": 0,
        }

    def test_a_failed_request_marks_its_batch_missing_and_goes_on(self) -> None:
        products = [Product("A", None), Product("B", None)]

        def complete(batch: list[Product]) -> str:
            if batch[0].name == "A":
                raise emoji_trial.GatewayError("timed out")
            return _answer([{"i": 1, "e": "🥦", "m": "exact", "why": "b"}])

        results = emoji_trial.run(products, REFERENCE, complete, batch_size=1)

        assert [r.match for r in results] == ["missing", "exact"]
        assert "timed out" in results[0].why

    def test_each_finished_batch_is_handed_over(self) -> None:
        products = [Product(f"P{n}", None) for n in range(3)]
        seen: list[int] = []

        def complete(batch: list[Product]) -> str:
            return _answer(
                [
                    {"i": i + 1, "e": None, "m": "none", "why": "x"}
                    for i in range(len(batch))
                ]
            )

        emoji_trial.run(
            products,
            REFERENCE,
            complete,
            batch_size=2,
            on_batch=lambda so_far: seen.append(len(so_far)),
        )

        assert seen == [2, 3]


class TestPostChat:
    def _post(self, handler: Any) -> str:
        return emoji_trial.post_chat(
            {"model": "m"},
            url="http://gateway/v1",
            api_key="k",
            timeout=5.0,
            transport=httpx.MockTransport(handler),
        )

    def test_it_returns_the_message_content(self) -> None:
        content = self._post(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "hi"}}]}
            )
        )

        assert content == "hi"

    @pytest.mark.parametrize(
        "body",
        [
            {"choices": [{"message": None}]},
            {"choices": []},
            {"choices": None},
            {},
            [],
        ],
    )
    def test_a_malformed_reply_is_a_gateway_error(self, body: Any) -> None:
        with pytest.raises(emoji_trial.GatewayError):
            self._post(lambda request: httpx.Response(200, json=body))

    def test_an_http_error_is_a_gateway_error(self) -> None:
        with pytest.raises(emoji_trial.GatewayError):
            self._post(lambda request: httpx.Response(503, text="busy"))


class TestOutput:
    RESULTS = [
        Result("Broccoli", "produce", "🥦", "exact", "broccoli"),
        Result("Entrecôte", "meat", "🥩", "borderline", "cut of meat is generic"),
        Result("Parsnip", "produce", None, "none", "no parsnip | emoji"),
        Result("Quark", "dairy", None, "invalid", "answered 🧆 outside the list"),
    ]

    def test_the_markdown_groups_by_match_with_counts(self) -> None:
        text = emoji_trial.render_markdown(self.RESULTS, title="Trial")

        assert text.startswith("# Trial")
        assert "exact 1 · borderline 1 · none 1 · invalid 1 · missing 0" in text
        exact = text.index("## Exact")
        borderline = text.index("## Borderline")
        gap = text.index("## Gap list")
        assert exact < borderline < gap
        assert "| Broccoli | produce | 🥦 | broccoli |" in text
        # A pipe in a cell must not break the table.
        assert "no parsnip \\| emoji" in text
        # Everything that is not exact needs a generated icon, borderline included until
        # the operator rules on it.
        gap_section = text[gap:]
        for name in ("Entrecôte", "Parsnip", "Quark"):
            assert name in gap_section
        assert "Broccoli" not in gap_section

    def test_it_writes_markdown_csv_and_json(self, tmp_path: Path) -> None:
        out = tmp_path / "emoji.md"

        written = emoji_trial.write_outputs(self.RESULTS, out, title="Trial")

        assert written == [out, tmp_path / "emoji.csv", tmp_path / "emoji.json"]
        rows = list(csv.DictReader((tmp_path / "emoji.csv").open(encoding="utf-8")))
        assert rows[0] == {
            "name": "Broccoli",
            "category": "produce",
            "emoji": "🥦",
            "match": "exact",
            "why": "broccoli",
        }
        data = json.loads((tmp_path / "emoji.json").read_text(encoding="utf-8"))
        assert data["counts"]["exact"] == 1
        assert data["results"][2]["emoji"] is None


class TestMain:
    def test_names_mode_runs_end_to_end_with_a_stubbed_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = tmp_path / "names.txt"
        names.write_text("Broccoli\nParsnip\n", encoding="utf-8")
        out = tmp_path / "out.md"
        seen: list[dict[str, Any]] = []

        def fake_post(payload: dict[str, Any], **_: Any) -> str:
            seen.append(payload)
            return _answer(
                [
                    {"i": 1, "e": "🥦", "m": "exact", "why": "broccoli"},
                    {"i": 2, "e": None, "m": "none", "why": "no parsnip"},
                ]
            )

        monkeypatch.setattr(emoji_trial, "post_chat", fake_post)

        code = emoji_trial.main(
            ["--names", str(names), "--out", str(out), "--model", "c2.test"]
        )

        assert code == 0
        assert len(seen) == 1
        assert seen[0]["model"] == "c2.test"
        assert "| Broccoli |" in out.read_text(encoding="utf-8")

    def test_names_and_from_db_are_exclusive(self) -> None:
        with pytest.raises(SystemExit):
            emoji_trial.main(["--names", "x", "--from-db"])

    def test_the_timeout_follows_llm_timeout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.core.config import settings

        names = tmp_path / "names.txt"
        names.write_text("Broccoli\n", encoding="utf-8")
        timeouts: list[float] = []

        def fake_post(payload: dict[str, Any], **kwargs: Any) -> str:
            timeouts.append(kwargs["timeout"])
            return _answer([{"i": 1, "e": "🥦", "m": "exact", "why": "b"}])

        monkeypatch.setattr(emoji_trial, "post_chat", fake_post)

        emoji_trial.main(["--names", str(names), "--out", str(tmp_path / "o.md")])

        assert timeouts == [settings.LLM_TIMEOUT]

    def test_finished_batches_survive_a_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = tmp_path / "names.txt"
        names.write_text("Broccoli\nParsnip\n", encoding="utf-8")
        out = tmp_path / "out.md"
        calls: list[int] = []

        def fake_post(payload: dict[str, Any], **_: Any) -> str:
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("console closed")
            return _answer([{"i": 1, "e": "🥦", "m": "exact", "why": "b"}])

        monkeypatch.setattr(emoji_trial, "post_chat", fake_post)

        with pytest.raises(RuntimeError):
            emoji_trial.main(
                ["--names", str(names), "--out", str(out), "--batch-size", "1"]
            )

        assert "| Broccoli |" in out.read_text(encoding="utf-8")

    def test_from_db_mode_reads_the_catalog_and_disposes_the_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeResult:
            def all(self) -> list[tuple[str, str]]:
                return [("Broccoli", "produce")]

        class FakeSession:
            async def execute(self, statement: Any, params: Any = None) -> FakeResult:
                return FakeResult()

        @asynccontextmanager
        async def sessions():  # type: ignore[no-untyped-def]
            yield FakeSession()

        disposed: list[bool] = []

        async def dispose() -> None:
            disposed.append(True)

        monkeypatch.setattr(emoji_trial, "_default_sessions", sessions)
        monkeypatch.setattr(emoji_trial, "_dispose_engine", dispose)
        monkeypatch.setattr(
            emoji_trial,
            "post_chat",
            lambda payload, **_: _answer(
                [{"i": 1, "e": "🥦", "m": "exact", "why": "b"}]
            ),
        )
        out = tmp_path / "db.md"

        code = emoji_trial.main(["--from-db", "--out", str(out), "--limit", "10"])

        assert code == 0
        assert disposed == [True]
        assert "| Broccoli | produce | 🥦 |" in out.read_text(encoding="utf-8")
