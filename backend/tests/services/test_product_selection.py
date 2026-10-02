"""The selection call's prompt and the reading of its answer (H13, H53).

The model may only choose among what a line was offered, and "none of these" has to be an
answer it actually gives: the reported pairs (Q14) were a small local model picking the
nearest candidate - Orange juice for pear juice, Taco sauce for taco shells - when the
right answer was null.
"""

import json
from uuid import UUID

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

# A line reached a candidate only through the model's g (Q37): one candidate is the
# rejected snap itself (F4, PR #153 review distinguishes it from an ordinary trigram
# candidate like "Raisin" here).
LINE_WITH_SNAP = SelectionLine(
    line_id="l2",
    printed="ALESTO SELECTION CASHEWP",
    generic="Dip",
    category="snacks",
    candidate_ids=(
        "0b0e9d2a-4c1f-4a5e-9e4b-1f1f1f1f1f03",
        "0b0e9d2a-4c1f-4a5e-9e4b-1f1f1f1f1f04",
    ),
    candidate_names=("Raisin", "Dip"),
    proposed_name="Dip",
)


def _answer(rows: list[dict]) -> str:
    return json.dumps({"r": rows})


class TestPrompt:
    def test_it_shows_a_null_answer(self) -> None:
        """H53: without an example of null, the model picks the nearest candidate."""
        assert '"p": null' in INSTRUCTIONS

    def test_a_shared_word_is_not_a_match(self) -> None:
        assert "Sharing a word" in INSTRUCTIONS

    def test_a_kind_used_the_same_way_is_a_match(self) -> None:
        """H53 live run: HUNAJAMELONI / Honeydew answered null against Melon in both
        runs - "different variety" read as any variety (docs/vLLM_MANUAL_TEST.md)."""
        assert "A named kind of the same food" in INSTRUCTIONS
        assert '"Granny Smith" is "Apple"' in INSTRUCTIONS

    def test_it_draws_one_line_between_same_and_different(self) -> None:
        """PR #99 review: "Different variety ... are DIFFERENT" sat directly above "a
        kind ... IS the same thing". The rule is what a cook buys and uses differently,
        and no sentence may call every variety different."""
        assert "buys and uses differently" in INSTRUCTIONS
        assert "Different variety" not in INSTRUCTIONS

    def test_its_examples_are_not_the_reported_pairs(self) -> None:
        """Otherwise the live test would grade the prompt on its own worked examples."""
        for word in ("Ketchup", "Taco", "Melon", "Pear"):
            assert word not in INSTRUCTIONS

    def test_its_examples_are_not_the_q37_reported_pairs(self) -> None:
        """Q37: the live test asks the model about butter vs Spread and turkey vs Ham
        among others - the prompt must not have told it the answer. ("Butter" and
        "Chicken" are not included: both were already general words in the prompt
        before Q37, for a different pairing.)"""
        for word in ("Pesto", "Cashew", "Spread", "Turkey", "Mozzarella", "Farfalle"):
            assert word not in INSTRUCTIONS

    def test_a_raw_ingredient_is_not_what_is_made_from_it(self) -> None:
        """Q37 live run: the model answered Spread for plain salted butter - a
        manufactured product is not its raw ingredient, however near on the shelf."""
        assert "is not a manufactured product made from it" in INSTRUCTIONS

    def test_one_animals_cut_is_not_anothers(self) -> None:
        """Q37 live run: the model answered Ham for turkey cold cuts."""
        assert "Meat from one animal is not the same product as a cut" in INSTRUCTIONS

    def test_a_processing_form_is_not_a_named_kind(self) -> None:
        """Q37 live run: the model answered Chicken fillet for chicken mince - a
        processed form read as a 'named kind' like Granny Smith is Apple."""
        glossary = " ".join(INSTRUCTIONS.split())
        assert "is not a named kind" in glossary
        assert '"Flour" is not "Wheat"' in glossary

    def test_a_broad_word_is_not_a_catch_all(self) -> None:
        """Q37 live run: the model answered Dip for cashew nuts and Chips for baking
        chocolate - a broad catalog word is not a match for everything that could be
        filed under it."""
        assert "is not a match for one specific thing" in INSTRUCTIONS

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
        answer = parse_selection(
            _answer([{"id": "l1", "p": LINE.candidate_ids[1]}]), [LINE]
        )

        assert str(answer.products["l1"]) == LINE.candidate_ids[1]

    def test_null_is_no_pick(self) -> None:
        answer = parse_selection(_answer([{"id": "l1", "p": None}]), [LINE])
        assert answer.products == {}
        assert answer.corrected == {}

    def test_a_product_it_was_not_offered_is_dropped(self) -> None:
        other = "0b0e9d2a-4c1f-4a5e-9e4b-1f1f1f1f1f99"

        answer = parse_selection(_answer([{"id": "l1", "p": other}]), [LINE])
        assert answer.products == {}

    def test_an_answer_without_a_result_list_is_an_error(self) -> None:
        with pytest.raises(LLMExtractionError):
            parse_selection(json.dumps({"r": "none"}), [LINE])

    # Q37b: a rejected g-only snap can carry a corrected generic name.
    def test_a_null_answer_may_carry_a_corrected_generic_name(self) -> None:
        answer = parse_selection(
            _answer([{"id": "l1", "p": None, "g": "Pear nectar"}]), [LINE]
        )

        assert answer.products == {}
        assert answer.corrected == {"l1": "Pear nectar"}

    def test_a_corrected_name_equal_to_a_non_proposed_candidate_is_kept(self) -> None:
        """F4 (PR #153 review): only the rejected *snap's* own name is a non-answer -
        an ordinary trigram candidate the model also declined is unrelated, and its
        name might genuinely be the correction, so `LINE` (no g-only snap among its
        candidates) must not throw this away."""
        answer = parse_selection(
            _answer([{"id": "l1", "p": None, "g": "Orange Juice"}]), [LINE]
        )

        assert answer.corrected == {"l1": "Orange Juice"}

    def test_a_corrected_name_equal_to_the_rejected_snaps_name_is_ignored(
        self,
    ) -> None:
        """Repeating back the g-only snap it was offered - and rejected - is not a
        correction."""
        answer = parse_selection(
            _answer([{"id": "l2", "p": None, "g": "Dip"}]), [LINE_WITH_SNAP]
        )

        assert answer.corrected == {}

    def test_the_snaps_name_is_ignored_case_and_whitespace_insensitively(
        self,
    ) -> None:
        answer = parse_selection(
            _answer([{"id": "l2", "p": None, "g": "  dip  "}]), [LINE_WITH_SNAP]
        )

        assert answer.corrected == {}

    def test_a_corrected_name_equal_to_a_different_candidate_on_a_snap_line_is_kept(
        self,
    ) -> None:
        """The snap line also offers an ordinary trigram candidate ("Raisin"); a
        correction that happens to equal that name is not repeating the rejected
        snap and is kept."""
        answer = parse_selection(
            _answer([{"id": "l2", "p": None, "g": "Raisin"}]), [LINE_WITH_SNAP]
        )

        assert answer.corrected == {"l2": "Raisin"}

    def test_a_corrected_name_alongside_a_pick_is_ignored(self) -> None:
        """`g` is only solicited for a null answer; a pick needs no correction."""
        answer = parse_selection(
            _answer([{"id": "l1", "p": LINE.candidate_ids[1], "g": "Something else"}]),
            [LINE],
        )

        assert answer.products == {"l1": UUID(LINE.candidate_ids[1])}
        assert answer.corrected == {}

    def test_a_blank_corrected_name_is_ignored(self) -> None:
        answer = parse_selection(_answer([{"id": "l1", "p": None, "g": "   "}]), [LINE])

        assert answer.corrected == {}

    def test_a_non_string_corrected_name_is_ignored(self) -> None:
        answer = parse_selection(_answer([{"id": "l1", "p": None, "g": 42}]), [LINE])

        assert answer.corrected == {}
