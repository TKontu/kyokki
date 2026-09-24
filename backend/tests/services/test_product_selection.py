"""The selection call's prompt and the reading of its answer (H13, H53).

The model may only choose among what a line was offered, and "none of these" has to be an
answer it actually gives: the reported pairs (Q14) were a small local model picking the
nearest candidate - Orange juice for pear juice, Taco sauce for taco shells - when the
right answer was null.
"""

import json

import pytest

from app.services.llm_extractor import LLMExtractionError
from app.services.product_selection import (
    INSTRUCTIONS,
    SelectionLine,
    build_prompt,
    parse_selection,
)

LINE = SelectionLine(
    line_id="l1",
    printed="PÄÄRYNÄMEHU 1L",
    generic="Pear juice",
    category="beverages",
    candidate_ids=(
        "0b0e9d2a-4c1f-4a5e-9e4b-1f1f1f1f1f01",
        "0b0e9d2a-4c1f-4a5e-9e4b-1f1f1f1f1f02",
    ),
    candidate_names=("Orange juice", "Apple juice"),
)


def _answer(rows: list[dict]) -> str:
    return json.dumps({"r": rows})


class TestPrompt:
    def test_it_shows_a_null_answer(self) -> None:
        """H53: without an example of null, the model picks the nearest candidate."""
        assert '"p": null' in INSTRUCTIONS

    def test_a_shared_word_is_not_a_match(self) -> None:
        assert "Sharing a word" in INSTRUCTIONS

    def test_its_examples_are_not_the_reported_pairs(self) -> None:
        """Otherwise the live test would grade the prompt on its own worked examples."""
        for word in ("Ketchup", "Taco", "Melon", "Pear"):
            assert word not in INSTRUCTIONS

    def test_it_carries_every_candidate_of_every_line(self) -> None:
        prompt = build_prompt([LINE])

        payload = json.loads(prompt[len(INSTRUCTIONS) :])
        assert payload == [
            {
                "id": "l1",
                "n": "PÄÄRYNÄMEHU 1L",
                "g": "Pear juice",
                "c": "beverages",
                "candidates": [
                    {"p": LINE.candidate_ids[0], "name": "Orange juice"},
                    {"p": LINE.candidate_ids[1], "name": "Apple juice"},
                ],
            }
        ]


class TestParse:
    def test_a_pick_among_the_candidates_is_kept(self) -> None:
        picked = parse_selection(
            _answer([{"id": "l1", "p": LINE.candidate_ids[1]}]), [LINE]
        )

        assert str(picked["l1"]) == LINE.candidate_ids[1]

    def test_null_is_no_pick(self) -> None:
        assert parse_selection(_answer([{"id": "l1", "p": None}]), [LINE]) == {}

    def test_a_product_it_was_not_offered_is_dropped(self) -> None:
        other = "0b0e9d2a-4c1f-4a5e-9e4b-1f1f1f1f1f99"

        assert parse_selection(_answer([{"id": "l1", "p": other}]), [LINE]) == {}

    def test_an_answer_without_a_result_list_is_an_error(self) -> None:
        with pytest.raises(LLMExtractionError):
            parse_selection(json.dumps({"r": "none"}), [LINE])
