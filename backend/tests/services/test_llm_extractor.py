"""Tests for the LLM receipt extractor (compact JSON contract proven in MVP-R0)."""

import base64
import json
import logging
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.services.llm_extractor import (
    MAX_KNOWN_PRODUCTS,
    RAW_COMPLETION_LIMIT,
    CategoryOption,
    LLMExtractionError,
    build_instructions,
    build_response_schema,
    extract_from_image,
    extract_from_text,
    extract_unaccounted_lines,
    number_receipt_lines,
    parse_completion,
    prefilter_receipt_text,
)

CATEGORIES = [
    CategoryOption(id="dairy", name="Dairy & Eggs"),
    CategoryOption(id="produce", name="Vegetables"),
]
CATEGORY_IDS = {c.id for c in CATEGORIES}

RECEIPT_TEXT = """S-KAUPAT
Prisma ruoan verkkokauppa
02.01.2026 11:40
----------------------------------------
KEVYTMAITOJUOMA LAKTON 1,28
BARISTA KAURAJUOMA 4,50
3 KPL 1,88 €/KPL
NORM. 5,64
ALENNUS -1,14
PUNASIPULI 0,52
0,330 KG 1,59 €/KG
TOIMITUSMAKSU 11,90 11,90
VERKKOK.PAKKAUSMATERIAALIMAKSU 2,55
----------------------------------------
VÄLISUMMA 173,92
YHTEENSÄ 173,92
BONUSTA KERRYTTÄVÄT OSTOK 173,92
MAKSUTAPA Korttimaksu
Kortti: Mastercard Credit
************6568
Veloitus: 173,92
Autentisointi: FW88SHFFHDVXS9G3
Viite: 1089366829
Aika: 02.01.2026 11:41
ALV VEROTON VERO VEROLLINEN
25,5% 31,13 7,93 39,06
YHT. 149,93 23,99 173,92"""


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


# A key to leave out of the answer, as an older model answer did
_ABSENT = object()


def _compact(**overrides) -> str:
    """A text answer in the production shape (Q27): lines cited, priced, `x`, `t`, `te`.

    PR #131 F21. Pass ``key=_ABSENT`` to leave a key out.
    """
    body = {
        "s": "S-KAUPAT",
        "d": "2026-01-02",
        "lc": "fi",
        "cc": "FI",
        "t": 2.46,
        "te": False,
        "p": [
            {
                "n": "KEVYTMAITOJUOMA LAKTON",
                "l": [3],
                "p": 1.29,
                "g": "Lactose-free milk",
                "q": 1,
                "w": None,
                "c": "dairy",
                "pw": None,
                "sl": 10,
                "os": 5,
            },
            {
                "n": "PUNASIPULI",
                "l": [4, 5],
                "p": 1.17,
                "g": "Red onion",
                "q": 1,
                "w": 0.33,
                "c": "produce",
                "pw": 110,
                "sl": 30,
                "os": None,
            },
        ],
        "x": [
            {"l": 1, "k": "header", "a": None},
            {"l": 6, "k": "total", "a": 2.46},
        ],
    }
    body.update(overrides)
    body = {k: v for k, v in body.items() if v is not _ABSENT}
    return json.dumps(body, ensure_ascii=False)


def _mock_client(response_json: dict | None = None, status: int = 200, raises=None):
    """Patch httpx.AsyncClient and return (patcher, post_mock)."""
    response = MagicMock()
    response.status_code = status
    response.json.return_value = response_json or _completion(_compact())
    if status >= 400:
        request = httpx.Request("POST", "http://llm/v1/chat/completions")
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=request, response=httpx.Response(status, request=request)
        )
    else:
        response.raise_for_status.return_value = None
    post = AsyncMock(side_effect=raises) if raises else AsyncMock(return_value=response)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = post
    return patch(
        "app.services.llm_extractor.httpx.AsyncClient", return_value=client
    ), post


class TestPrefilter:
    def test_keeps_totals_payment_vat_discount_and_fee_lines(self):
        """Q27: the Finnish skip patterns no longer decide what any receipt's model sees.

        The total must reach the model for the arithmetic check, and a line one country
        skips can be a product in another.
        """
        filtered = prefilter_receipt_text(RECEIPT_TEXT)
        for kept in (
            "YHTEENSÄ",
            "VÄLISUMMA",
            "BONUSTA",
            "Kortti:",
            "Veloitus:",
            "Viite:",
            "ALV ",
            "25,5%",
            "YHT.",
            "NORM.",
            "ALENNUS",
            "TOIMITUSMAKSU",
            "VERKKOK.PAKKAUS",
            "*****",
            "-----",
        ):
            assert kept in filtered, kept

    def test_drops_only_blank_lines(self):
        assert prefilter_receipt_text("A 1,00\n\n   \nYHTEENSÄ 1,00\n") == (
            "A 1,00\nYHTEENSÄ 1,00"
        )

    def test_keeps_header_products_and_quantity_lines(self):
        filtered = prefilter_receipt_text(RECEIPT_TEXT)
        for kept in (
            "S-KAUPAT",
            "02.01.2026 11:40",
            "KEVYTMAITOJUOMA LAKTON 1,28",
            "3 KPL 1,88 €/KPL",
            "0,330 KG 1,59 €/KG",
        ):
            assert kept in filtered, kept


class TestResponseSchema:
    def test_constrains_category_to_given_ids_or_null(self):
        schema = build_response_schema(["dairy", "produce"])
        item = schema["properties"]["p"]["items"]
        assert item["properties"]["c"]["enum"] == [
            "dairy",
            "produce",
            "household",
            None,
        ]
        assert item["properties"]["g"] == {"type": "string"}
        # Q27 (amendment 1): every product cites its lines and its line total, and the
        # answer lists the other lines, the total, and the receipt's language and country
        assert item["required"] == [
            "n",
            "l",
            "p",
            "g",
            "q",
            "w",
            "c",
            "pw",
            "sl",
            "os",
        ]
        assert item["properties"]["l"] == {
            "type": "array",
            "items": {"type": "integer"},
        }
        assert item["properties"]["p"] == {"type": ["number", "null"]}
        assert item["properties"]["pw"] == {"type": ["number", "null"]}
        assert item["properties"]["sl"] == {"type": ["integer", "null"]}
        assert item["properties"]["os"] == {"type": ["integer", "null"]}
        # te (Q27 verdict #18): whether the tax is added on top of the line totals
        assert schema["required"] == ["s", "d", "lc", "cc", "t", "te", "p", "x"]
        other = schema["properties"]["x"]["items"]
        assert other["required"] == ["l", "k", "a"]
        assert other["properties"]["k"]["enum"] == [
            "header",
            "total",
            "subtotal",
            "tax",
            "payment",
            "discount",
            "deposit",
            "fee",
            "other",
        ]


class TestParseCompletion:
    def test_maps_compact_keys(self):
        result = parse_completion(_compact(), CATEGORY_IDS, method="text")
        assert isinstance(result, ReceiptExtraction)
        assert result.method == "text"
        assert result.store_chain == "S-KAUPAT"
        assert result.purchase_date == date(2026, 1, 2)
        assert result.lines == [
            ExtractedLine(
                name="KEVYTMAITOJUOMA LAKTON",
                generic_name="Lactose-free milk",
                quantity=1,
                weight_kg=None,
                category="dairy",
                shelf_life_days=10,
                opened_shelf_life_days=5,
                source_lines=[3],
                price=1.29,
            ),
            ExtractedLine(
                name="PUNASIPULI",
                generic_name="Red onion",
                quantity=1,
                weight_kg=0.33,
                piece_grams=110,
                shelf_life_days=30,
                category="produce",
                source_lines=[4, 5],
                price=1.17,
            ),
        ]
        assert [(o.line, o.kind, o.amount) for o in result.other_lines] == [
            (1, "header", None),
            (6, "total", 2.46),
        ]
        assert (result.receipt_total, result.tax_exclusive) == (2.46, False)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  ground   beef ", "Ground beef"),
            ("Low-fat milk", "Low-fat milk"),
            ("", None),
            ("   ", None),
            (None, None),
        ],
    )
    def test_generic_name_is_tidied(self, raw, expected):
        content = json.dumps(
            {"s": None, "d": None, "p": [{"n": "SNELLMAN JAUHELIHA", "g": raw, "q": 1}]}
        )
        result = parse_completion(content, CATEGORY_IDS, method="text")
        assert result.lines[0].generic_name == expected

    def test_missing_generic_name_is_none(self):
        content = json.dumps({"s": None, "d": None, "p": [{"n": "PUNASIPULI", "q": 1}]})
        result = parse_completion(content, CATEGORY_IDS, method="text")
        assert result.lines[0].generic_name is None


class TestInstructions:
    def test_ask_for_a_generic_english_name(self):
        text = build_instructions(CATEGORIES)
        assert "g = " in text
        assert "English" in text
        assert "Ground beef" in text

    def test_ask_for_singular_names(self):
        """Plural and singular names would become two products (MVP-R2 reuse is by name)."""
        text = build_instructions(CATEGORIES)
        assert "singular" in text
        assert '"Apples"' in text

    def test_name_household_products_too(self):
        text = build_instructions(CATEGORIES)
        assert "Cleaning cloth" in text
        assert "Laundry vinegar" in text

    def test_carry_a_finnish_glossary(self):
        """H54: TUMMA RYPÄLE came back as Raisin, TIKKUPERUNAT as Potato (Q14).

        Measured before and after on the 49-line fixture (docs/vLLM_MANUAL_TEST.md).
        Each mapping is pinned as written, not as words found anywhere in the prompt:
        "juice" and "grape" would be there without the glossary.
        """
        glossary = " ".join(build_instructions(CATEGORIES).split())
        assert 'TUMMA RYPÄLE -> "Grape"' in glossary
        assert 'RUSINA is "Raisin"' in glossary
        assert 'TIKKUPERUNAT -> "French fries"' in glossary
        assert 'RIISIPIIRAKKA -> "Karelian pasty"' in glossary
        assert "VALMISRUOKA, ATERIA -> c = ready_meals" in glossary

    def test_the_glossary_maps_mehu_to_a_juice_of_its_fruit(self):
        """Attempt 1's bare "MEHU = juice" flattened TÄYSMEHU OMENA to plain Juice."""
        glossary = " ".join(build_instructions(CATEGORIES).split())
        assert 'TÄYSMEHU OMENA -> "Apple juice" (MEHU is juice)' in glossary

    def test_the_glossary_keeps_a_multivitamin_supplement_out_of_juice(self):
        """NAMIVITA MONIVITAMIINI is a supplement; MONIVITAMIINI APPELSIINI is a juice."""
        glossary = " ".join(build_instructions(CATEGORIES).split())
        assert 'MONIVITAMIINI APPELSIINI -> "Multivitamin juice"' in glossary
        assert (
            "MONIVITAMIINI with no flavour is a vitamin supplement, household"
            in glossary
        )

    def test_ask_for_a_shelf_life_on_every_food_line(self):
        """With the glossary added, 3 of 7 runs answered sl only for the prompt's own
        examples (6-10 of 49 instead of 39-41). Saying the examples are not the list
        brought it back to 41 of 49 on 4 runs of 4 (H54, docs/vLLM_MANUAL_TEST.md)."""
        text = build_instructions(CATEGORIES)
        assert "for every food line, not only these" in text

    def test_list_known_products_to_reuse_their_names(self):
        text = build_instructions(CATEGORIES, ["Milk", "Ground beef", "milk"])
        assert "Known products: Ground beef, Milk." in text

    def test_without_known_products_the_list_is_omitted(self):
        assert "Known products" not in build_instructions(CATEGORIES)

    def test_the_catalog_block_can_be_turned_off(self, monkeypatch):
        """H17 measured dropping it: 49 of 49 lines and generic names survive, but the
        categories the model fills in fall from 40 to ~30, so it stays on by default
        and this setting exists to turn it off (docs/vLLM_MANUAL_TEST.md)."""
        monkeypatch.setattr(settings, "EXTRACTION_OFFERS_CATALOG", False)

        text = build_instructions(CATEGORIES, ["Milk", "Ground beef"])

        assert "Known products" not in text

    def test_the_catalog_block_is_on_by_default(self):
        assert settings.EXTRACTION_OFFERS_CATALOG is True

    def test_known_products_are_capped(self):
        names = [f"Product {i:04d}" for i in range(MAX_KNOWN_PRODUCTS + 50)]
        text = build_instructions(CATEGORIES, names)
        assert f"Product {MAX_KNOWN_PRODUCTS - 1:04d}" in text
        assert f"Product {MAX_KNOWN_PRODUCTS:04d}" not in text

    def test_strips_reasoning_and_code_fences(self):
        content = f"<think>let me read the receipt</think>\n```json\n{_compact()}\n```"
        assert len(parse_completion(content, CATEGORY_IDS, method="vision").lines) == 2

    def test_strips_trailing_prices_from_names(self):
        content = _compact(p=[{"n": "LIME 2,21", "q": 1, "w": 0.74, "c": None}])
        assert (
            parse_completion(content, CATEGORY_IDS, method="text").lines[0].name
            == "LIME"
        )

    def test_unknown_category_becomes_none(self):
        # "household" used to stand in for "unknown"; it is a non-food sentinel now (Q1)
        content = _compact(p=[{"n": "KALA", "q": 2, "w": None, "c": "seafood"}])
        assert (
            parse_completion(content, CATEGORY_IDS, method="text").lines[0].category
            is None
        )

    def test_invalid_or_missing_date_and_store_become_none(self):
        result = parse_completion(
            _compact(s="", d="02.01.2026"), CATEGORY_IDS, method="text"
        )
        assert result.store_chain is None
        assert result.purchase_date is None

    def test_drops_entries_without_a_name(self):
        content = _compact(
            p=[{"n": " ", "q": 1, "w": None, "c": None}, {"n": "KURKKU", "q": 1}]
        )
        lines = parse_completion(content, CATEGORY_IDS, method="text").lines
        assert [line.name for line in lines] == ["KURKKU"]
        assert lines[0].weight_kg is None

    @pytest.mark.parametrize(
        "content", ["not json at all", '{"s": null, "d": null}', '{"p": "x"}']
    )
    def test_malformed_output_raises(self, content):
        with pytest.raises(LLMExtractionError):
            parse_completion(content, CATEGORY_IDS, method="text")


class TestExtractFromText:
    async def test_sends_the_r0_request(self):
        patcher, post = _mock_client()
        with patcher:
            result = await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert len(result.lines) == 2
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        assert url == f"{settings.LLM_BASE_URL}/chat/completions"
        assert payload["model"] == settings.LLM_MODEL
        assert payload["max_tokens"] == settings.LLM_MAX_TOKENS
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        schema = payload["response_format"]["json_schema"]["schema"]
        assert schema["properties"]["p"]["items"]["properties"]["c"]["enum"] == [
            "dairy",
            "produce",
            "household",
            None,
        ]
        assert payload["chat_template_kwargs"] == {
            "reasoning_strength": settings.LLM_REASONING_STRENGTH
        }

    async def test_prompt_is_prefiltered_and_names_categories(self):
        patcher, post = _mock_client()
        with patcher:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        assert isinstance(prompt, str)
        assert "KEVYTMAITOJUOMA LAKTON 1,28" in prompt
        # the printed total reaches the model now, for the arithmetic check (Q27)
        assert "YHTEENSÄ 173,92" in prompt
        assert "dairy (Dairy & Eggs)" in prompt

    async def test_known_products_reach_the_prompt(self):
        patcher, post = _mock_client()
        with patcher:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES, ["Red onion"])

        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        assert "Known products: Red onion." in prompt

    async def test_reasoning_kwargs_omitted_when_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_REASONING_STRENGTH", None)
        patcher, post = _mock_client()
        with patcher:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)
        assert "chat_template_kwargs" not in post.call_args.kwargs["json"]

    async def test_http_error_raises_extraction_error(self):
        patcher, _ = _mock_client(status=500)
        with patcher, pytest.raises(LLMExtractionError):
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

    async def test_timeout_raises_extraction_error(self):
        patcher, _ = _mock_client(raises=httpx.ReadTimeout("slow"))
        with patcher, pytest.raises(LLMExtractionError):
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

    async def test_missing_choices_raises_extraction_error(self):
        patcher, _ = _mock_client(response_json={"error": "model not found"})
        with patcher, pytest.raises(LLMExtractionError):
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)


class TestExtractFromImage:
    async def test_sends_text_and_image_parts(self):
        image = b"\x89PNG fake image bytes"
        patcher, post = _mock_client()
        with patcher:
            result = await extract_from_image(image, "image/png", CATEGORIES)

        assert result.method == "vision"
        parts = post.call_args.kwargs["json"]["messages"][0]["content"]
        assert [part["type"] for part in parts] == ["text", "image_url"]
        assert "dairy (Dairy & Eggs)" in parts[0]["text"]
        expected = "data:image/png;base64," + base64.b64encode(image).decode()
        assert parts[1]["image_url"]["url"] == expected


class TestProductShapeFields:
    """Q2/Q6: the model also estimates what one piece weighs and how long it keeps."""

    def test_asks_for_a_piece_weight_with_examples(self):
        text = build_instructions(CATEGORIES)
        assert "pw = " in text
        assert "apple -> 125" in text

    def test_asks_for_a_shelf_life_with_examples(self):
        text = build_instructions(CATEGORIES)
        assert "sl = " in text
        assert "banana -> 7" in text

    def test_maps_both_onto_the_line(self):
        result = parse_completion(_compact(), {"dairy", "produce"}, "text")

        milk, onion = result.lines
        assert (milk.piece_grams, milk.shelf_life_days) == (None, 10)
        assert (onion.piece_grams, onion.shelf_life_days) == (110.0, 30)

    def test_missing_fields_are_none(self):
        """Older receipts and the heuristic parser have neither."""
        body = json.dumps({"p": [{"n": "OMENA", "g": "Apple", "q": 1}]})

        (line,) = parse_completion(body, set(), "text").lines

        assert line.piece_grams is None
        assert line.shelf_life_days is None

    @pytest.mark.parametrize("bad", [0, -5, "many", True, None])
    def test_a_nonsense_estimate_is_dropped_not_stored(self, bad):
        """A zero piece weight would divide a real purchase into nothing."""
        body = json.dumps(
            {"p": [{"n": "OMENA", "g": "Apple", "q": 1, "pw": bad, "sl": bad}]}
        )

        (line,) = parse_completion(body, set(), "text").lines

        assert line.piece_grams is None
        assert line.shelf_life_days is None

    def test_a_fractional_shelf_life_becomes_whole_days(self):
        body = json.dumps({"p": [{"n": "OMENA", "g": "Apple", "q": 1, "sl": 6.7}]})

        (line,) = parse_completion(body, set(), "text").lines

        assert line.shelf_life_days == 7


class TestOpenedShelfLife:
    """Q5: how long a pack keeps once it is opened."""

    def test_asks_for_it_with_examples(self):
        text = build_instructions(CATEGORIES)
        assert "os = " in text
        assert "milk -> 5" in text

    def test_a_known_catalog_never_talks_the_model_out_of_estimating(self):
        """This assertion is the exact reverse of the one it replaces.

        The block used to end "and set pw, sl and os to null for it - the system
        already knows those", to save re-deriving what the catalog holds. Measured on
        the 49-line fixture, offering any catalog at all then dropped shelf lives from
        39 of 49 to between 1 and 12, and opened shelf lives from 17 to between 1 and 7
        - the model applied the instruction to the whole receipt, not to the listed
        products. Every product created from a receipt read with a warm catalog fell
        back to its category's blanket shelf life, which is the thing Q6 exists to
        avoid (Q7, docs/vLLM_MANUAL_TEST.md).
        """
        text = build_instructions(CATEGORIES, ["Apple", "Milk"])

        assert "Known products: Apple, Milk." in text
        assert "null for it" not in text
        assert "already knows those" not in text

    def test_an_empty_catalog_offers_no_block_at_all(self):
        text = build_instructions(CATEGORIES)

        assert "Known products" not in text

    def test_maps_it_onto_the_line(self):
        milk, onion = parse_completion(_compact(), {"dairy", "produce"}, "text").lines

        assert milk.opened_shelf_life_days == 5
        assert onion.opened_shelf_life_days is None

    @pytest.mark.parametrize("bad", [0, -3, "soon", None])
    def test_a_nonsense_estimate_is_dropped(self, bad):
        body = json.dumps({"p": [{"n": "MAITO", "g": "Milk", "q": 1, "os": bad}]})

        (line,) = parse_completion(body, set(), "text").lines

        assert line.opened_shelf_life_days is None


class TestCategoryMatching:
    """The gateway does not always honour the strict enum, and a miss nulls the category."""

    def test_a_differently_cased_category_still_matches(self):
        """muse-glimmer answers "Dairy" for the id `dairy`; a case-sensitive test lost all 49."""
        body = json.dumps(
            {
                "p": [
                    {"n": "MAITO", "g": "Milk", "q": 1, "c": "Dairy"},
                    {"n": "OMENA", "g": "Apple", "q": 1, "c": "PRODUCE"},
                ]
            }
        )

        milk, apple = parse_completion(body, {"dairy", "produce"}, "text").lines

        assert milk.category == "dairy"
        assert apple.category == "produce"

    def test_a_category_that_is_not_ours_is_still_dropped(self):
        # Not "household": that is a sentinel now, and TestNonFood covers it
        body = json.dumps({"p": [{"n": "KALA", "g": "Fish", "q": 1, "c": "seafood"}]})

        (line,) = parse_completion(body, {"dairy"}, "text").lines

        assert line.category is None


class TestNonFood:
    """Q1: the model already says "household"; stop throwing the answer away."""

    def test_the_schema_offers_the_sentinel(self):
        item = build_response_schema(["dairy"])["properties"]["p"]["items"]

        assert item["properties"]["c"]["enum"] == ["dairy", "household", None]

    def test_the_prompt_asks_for_it(self):
        assert "Answer household for their c" in build_instructions(CATEGORIES)

    def test_a_household_line_is_marked_not_food(self):
        body = json.dumps(
            {
                "p": [
                    {"n": "SIENILIINA", "g": "Cleaning cloth", "q": 1, "c": "household"}
                ]
            }
        )

        (line,) = parse_completion(body, {"dairy"}, "text").lines

        assert line.non_food is True
        assert line.category is None

    def test_the_sentinel_is_matched_on_case_like_any_other(self):
        body = json.dumps(
            {"p": [{"n": "SIENILIINA", "g": "Cloth", "q": 1, "c": "Household"}]}
        )

        (line,) = parse_completion(body, {"dairy"}, "text").lines

        assert line.non_food is True

    def test_a_food_line_is_not_marked(self):
        body = json.dumps({"p": [{"n": "MAITO", "g": "Milk", "q": 1, "c": "dairy"}]})

        (line,) = parse_completion(body, {"dairy"}, "text").lines

        assert line.non_food is False
        assert line.category == "dairy"

    def test_a_category_we_do_not_know_is_still_only_dropped(self):
        """Unknown is not the same as not food: the model simply failed to file it."""
        body = json.dumps(
            {"p": [{"n": "KUMMA", "g": "Something", "q": 1, "c": "seafood"}]}
        )

        (line,) = parse_completion(body, {"dairy"}, "text").lines

        assert line.category is None
        assert line.non_food is False


class TestCatalogIsANamingAidOnly:
    """Q27: a warm-catalog read returned only the six listed products; the old catalog
    wording is the prime suspect for that loss, not a proven cause."""

    def test_the_block_asks_for_every_line_listed_or_not(self):
        text = build_instructions(CATEGORIES, ["Potato", "Hummus"])

        assert "whether or not it is in this list" in text
        assert "only tells you which name to use" in text
        assert "Known products: Hummus, Potato." in text

    def test_without_a_catalog_there_is_no_block(self):
        text = build_instructions(CATEGORIES)
        assert "whether or not it is in this list" not in text

    def test_a_listed_name_is_for_the_same_product_only(self):
        """Q37: a listed name 'equivalent' read too loosely and cashew nuts, butter and
        pesto all snapped to Dip or Spread. The block now names the same test g itself
        uses and says a listed name of a different food is wrong even with nothing
        closer listed."""
        text = " ".join(build_instructions(CATEGORIES, ["Dip"]).split())
        assert "would a home cook put them on one shopping-list line" in text
        assert "wrong even when the list offers nothing closer" in text

    def test_the_wrongness_rule_is_general_not_receipt_specific(self):
        """No hardcoded receipt formats or languages (project standing rule): the new
        sentence must read as a general rule, not cite the Lidl fixture's products."""
        text = build_instructions(CATEGORIES, ["Dip"])
        for word in ("Pesto", "Cashew", "Dip spice", "Kalkkuna", "Jauhel"):
            assert word not in text


class TestLanguageNeutralRules:
    """Amendment 1: receipts from any country; Finnish strings only as examples."""

    def test_count_and_weight_lines_are_general_rules_with_examples(self):
        text = " ".join(build_instructions(CATEGORIES).split())
        assert "gives a count and a unit price means q = that count" in text
        assert "gives a weight and a price per kg or lb means w = that weight" in text
        assert 'Examples: "3 KPL 1,88 €/KPL" below the name; "2 x 1,49" above' in text

    def test_the_glossary_is_labelled_as_examples(self):
        text = " ".join(build_instructions(CATEGORIES).split())
        assert "Examples of Finnish words often misread: TUMMA RYPÄLE" in text

    def test_asks_to_account_for_every_numbered_line(self):
        text = " ".join(build_instructions(CATEGORIES).split())
        assert "Every line that carries an amount" in text
        assert "lines without any amount need not be listed" in text
        assert "whether that line comes before or after the name" in text
        assert "never the unit price" in text
        assert "lc = the receipt's language" in text


class TestNumberedLines:
    def test_every_non_blank_line_is_numbered(self):
        numbered = number_receipt_lines(RECEIPT_TEXT)

        assert numbered[0] == (1, "S-KAUPAT")
        assert (16, "YHTEENSÄ 173,92") in numbered
        assert [n for n, _ in numbered] == list(range(1, len(numbered) + 1))

    async def test_the_prompt_shows_the_numbers(self):
        patcher, post = _mock_client()
        with patcher:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
        assert "\n1: S-KAUPAT\n" in prompt
        assert "6: BARISTA KAURAJUOMA 4,50\n7: 3 KPL 1,88 €/KPL" in prompt


class TestAccountingFields:
    def test_maps_line_numbers_prices_other_lines_total_and_locale(self):
        content = json.dumps(
            {
                "s": "K-Citymarket",
                "d": None,
                "lc": "fi",
                "cc": "FI",
                "t": 26.82,
                "p": [
                    {"n": "Naudan Entrecote Palana", "l": [5, 4, 4], "p": 22.83},
                    {"n": "Palsternakka", "l": "4", "p": "1,04"},
                ],
                "x": [
                    {"l": 1, "k": "header", "a": None},
                    {"l": 9, "k": "Discount", "a": -0.5},
                    {"l": 10, "k": "loyalty", "a": 3.0},
                    {"l": "x", "k": "total", "a": 26.82},
                    "junk",
                ],
            }
        )

        result = parse_completion(content, CATEGORY_IDS, method="text")

        entrecote, parsnip = result.lines
        assert (entrecote.source_lines, entrecote.price) == ([4, 5], 22.83)
        assert (parsnip.source_lines, parsnip.price) == ([], None)
        assert [(o.line, o.kind, o.amount) for o in result.other_lines] == [
            (1, "header", None),
            (9, "discount", -0.5),
            (10, "other", 3.0),
        ]
        assert result.receipt_total == 26.82
        assert (result.language, result.country) == ("fi", "FI")

    def test_older_answers_without_the_fields_still_parse(self):
        older = json.loads(_compact(lc=_ABSENT, cc=_ABSENT, t=_ABSENT, x=_ABSENT))
        for product in older["p"]:
            del product["l"], product["p"]
        result = parse_completion(json.dumps(older), CATEGORY_IDS, method="text")

        assert all(line.source_lines == [] for line in result.lines)
        assert result.other_lines == []
        assert result.receipt_total is None
        assert (result.language, result.country) == (None, None)


class TestNothingIsDroppedSilently:
    def test_unusable_entries_are_counted(self):
        content = _compact(
            p=[
                "not an object",
                {"n": " ", "q": 1},
                # a negative quantity fails ExtractedLine validation
                {"n": "KURKKU", "q": -1},
                {"n": "PORKKANA", "q": 1},
            ]
        )

        result = parse_completion(content, CATEGORY_IDS, method="text")

        assert [line.name for line in result.lines] == ["PORKKANA"]
        assert result.invalid_entries == 3

    def test_a_validation_error_is_counted_and_logged(self, caplog):
        content = _compact(p=[{"n": "KURKKU", "q": 1, "w": -0.5}])

        result = parse_completion(content, CATEGORY_IDS, method="text")

        assert result.lines == []
        assert result.invalid_entries == 1
        assert any(
            r.levelname == "WARNING" and "invalid" in r.getMessage().lower()
            for r in caplog.records
        )

    def test_a_clean_answer_has_no_invalid_entries(self):
        result = parse_completion(_compact(), CATEGORY_IDS, method="text")
        assert result.invalid_entries == 0

    async def test_a_truncated_answer_raises(self):
        response = _completion(_compact())
        response["choices"][0]["finish_reason"] = "length"
        patcher, _ = _mock_client(response_json=response)

        with patcher, pytest.raises(LLMExtractionError, match="truncated"):
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

    async def test_a_finished_answer_is_accepted(self):
        response = _completion(_compact())
        response["choices"][0]["finish_reason"] = "stop"
        patcher, _ = _mock_client(response_json=response)

        with patcher:
            result = await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert len(result.lines) == 2

    async def test_the_raw_completion_is_kept(self):
        patcher, _ = _mock_client()

        with patcher:
            result = await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert result.raw_completion == _compact()

    async def test_the_raw_completion_is_capped_at_64_kb(self):
        padded = _compact() + " " * (2 * RAW_COMPLETION_LIMIT)
        patcher, _ = _mock_client(response_json=_completion(padded))

        with patcher:
            result = await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert RAW_COMPLETION_LIMIT == 64 * 1024
        assert len(result.raw_completion.encode("utf-8")) <= RAW_COMPLETION_LIMIT
        assert result.raw_completion.startswith(_compact())

    async def test_the_raw_completion_is_not_logged_at_info(self, caplog):
        caplog.set_level("DEBUG")
        patcher, _ = _mock_client()

        with patcher:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        for record in caplog.records:
            if record.levelno >= logging.INFO:
                assert "KEVYTMAITOJUOMA" not in str(record.__dict__)


class TestExtractUnaccountedLines:
    """Q27: one targeted call for the lines the first read left out."""

    MISSING = [(9, "Palsternakka 1,04"), (10, "0,523 KG 1,99 €/KG")]

    async def test_asks_about_these_lines_without_the_catalog(self, monkeypatch):
        patcher, post = _mock_client()

        with patcher:
            result = await extract_unaccounted_lines(self.MISSING, CATEGORIES)

        assert len(result.lines) == 2
        payload = post.call_args.kwargs["json"]
        prompt = payload["messages"][0]["content"]
        assert "were not accounted for" in prompt
        # a name line and its detail line go together, with their own numbers
        assert "9: Palsternakka 1,04\n10: 0,523 KG 1,99 €/KG" in prompt
        assert "Known products" not in prompt
        assert "dairy (Dairy & Eggs)" in prompt
        # the same contract as the first read
        assert payload["response_format"]["json_schema"]["schema"] == (
            build_response_schema(["dairy", "produce"])
        )

    async def test_failure_raises_like_any_read(self):
        patcher, _ = _mock_client(status=500)

        with patcher, pytest.raises(LLMExtractionError):
            await extract_unaccounted_lines(self.MISSING, CATEGORIES)


class TestFailedAnswersArePersisted:
    """Q27 verdict #13 and #19: the answers most worth diagnosing are kept."""

    async def test_a_truncated_answer_carries_its_raw_completion(self):
        response = _completion('{"p": [{"n": "MAITO"')
        response["choices"][0]["finish_reason"] = "length"
        patcher, _ = _mock_client(response_json=response)

        with patcher, pytest.raises(LLMExtractionError) as caught:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert caught.value.raw_completion == '{"p": [{"n": "MAITO"'

    async def test_an_unparseable_answer_carries_its_raw_completion(self):
        patcher, _ = _mock_client(response_json=_completion("I cannot read this"))

        with patcher, pytest.raises(LLMExtractionError) as caught:
            await extract_unaccounted_lines([(3, "MAITO 1,20")], CATEGORIES)

        assert caught.value.raw_completion == "I cannot read this"

    async def test_a_non_json_http_200_body_is_an_extraction_error(self):
        """The body itself is not JSON: `response.json()` raised past the handler and
        failed the receipt."""
        patcher, post = _mock_client()
        response = post.return_value
        response.json.side_effect = json.JSONDecodeError("Expecting value", "<", 0)
        response.text = "<html>gateway restarting</html>"

        with patcher, pytest.raises(LLMExtractionError) as caught:
            await extract_unaccounted_lines([(3, "MAITO 1,20")], CATEGORIES)

        assert caught.value.raw_completion == "<html>gateway restarting</html>"

    async def test_a_failed_answer_is_capped_too(self):
        huge = "x" * (2 * RAW_COMPLETION_LIMIT)
        patcher, _ = _mock_client(response_json=_completion(huge))

        with patcher, pytest.raises(LLMExtractionError) as caught:
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert len(caught.value.raw_completion.encode("utf-8")) == RAW_COMPLETION_LIMIT

    def test_an_error_without_an_answer_has_none(self):
        assert LLMExtractionError("gateway down").raw_completion is None


class TestVisionListsPricedNonProducts:
    """Q27 verdict #6: a photo with a deposit or discount must not show a false gap."""

    def test_the_prompt_asks_for_x_on_an_image_too(self):
        text = " ".join(build_instructions(CATEGORIES).split())
        assert "On an image there are no line numbers" in text
        assert "still list each priced non-product line in x with l = null" in text

    def test_the_schema_allows_an_x_entry_without_a_line_number(self):
        schema = build_response_schema(["dairy"])
        assert schema["properties"]["x"]["items"]["properties"]["l"] == {
            "type": ["integer", "null"]
        }

    def test_a_vision_answer_keeps_x_without_line_numbers(self):
        content = _compact(
            x=[
                {"l": None, "k": "deposit", "a": 0.25},
                {"l": None, "k": "total", "a": 3},
            ]
        )

        result = parse_completion(content, CATEGORY_IDS, method="vision")

        assert [(o.line, o.kind, o.amount) for o in result.other_lines] == [
            (None, "deposit", 0.25),
            (None, "total", 3.0),
        ]

    def test_a_text_answer_still_needs_the_line_number(self):
        content = _compact(x=[{"l": None, "k": "deposit", "a": 0.25}])

        result = parse_completion(content, CATEGORY_IDS, method="text")

        assert result.other_lines == []


class TestTaxExclusiveTotals:
    """Q27 verdict #18: a US receipt adds the tax after the line totals."""

    def test_the_schema_and_prompt_ask_for_te(self):
        schema = build_response_schema(["dairy"])
        assert schema["properties"]["te"] == {"type": "boolean"}
        assert "te" in schema["required"]
        text = " ".join(build_instructions(CATEGORIES).split())
        assert "te = true when the line totals do not include the tax" in text

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, True), (False, False), (None, False), ("yes", False)],
    )
    def test_te_maps_to_tax_exclusive(self, value, expected):
        result = parse_completion(_compact(te=value), CATEGORY_IDS, method="text")
        assert result.tax_exclusive is expected

    def test_an_answer_without_te_is_tax_inclusive(self):
        answer = _compact(te=_ABSENT)
        assert parse_completion(answer, CATEGORY_IDS, "text").tax_exclusive is False


class TestLanguageAndCountryCodes:
    """Q27 verdict #26: "FIN" or "fi-FI" silently ran with no profile."""

    @pytest.mark.parametrize(
        ("lc", "expected"),
        [
            ("fi", "fi"),
            ("FI", "fi"),
            ("fin", "fi"),
            ("fi-FI", "fi"),
            ("de_DE", "de"),
            ("hrv", "hr"),
            ("eng", "en"),
            ("Finnish", None),
            ("zzz", None),
            ("f", None),
            # PR #131 F17: only real ISO 639-1 codes
            ("xx", None),
            ("qq-FI", None),
            (None, None),
            (7, None),
        ],
    )
    def test_language(self, lc, expected):
        result = parse_completion(_compact(lc=lc), CATEGORY_IDS, "text")
        assert result.language == expected

    @pytest.mark.parametrize(
        ("cc", "expected"),
        [
            ("FI", "FI"),
            ("fi", "FI"),
            ("FIN", "FI"),
            ("fi-FI", "FI"),
            ("en_US", "US"),
            ("USA", "US"),
            ("DEU", "DE"),
            ("Finland", None),
            ("XYZ", None),
            ("", None),
            # PR #131 F17: only real ISO 3166-1 codes; UK is the common alias of GB
            ("UK", "GB"),
            ("en-UK", "GB"),
            ("xx", None),
            ("QQ", None),
        ],
    )
    def test_country(self, cc, expected):
        result = parse_completion(_compact(cc=cc), CATEGORY_IDS, "text")
        assert result.country == expected


class TestPromptTextMatchesTheContract:
    """Q27 verdict #21: the re-read asked for "every other line" in x."""

    async def test_the_re_read_lists_only_priced_non_products(self):
        patcher, post = _mock_client()

        with patcher:
            await extract_unaccounted_lines([(3, "MAITO 1,20")], CATEGORIES)

        content = post.call_args.kwargs["json"]["messages"][0]["content"]
        prompt = " ".join(content.split())
        assert "every other one of these lines" not in prompt
        assert "list each of these lines that carries an amount and is not" in prompt


def _client_class_answering(client_class: MagicMock, content: str) -> None:
    client = client_class.return_value
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    response = MagicMock()
    response.json.return_value = _completion(content)
    client.post = AsyncMock(return_value=response)


class TestEstimateTimeout:
    """Q27 verdict #17: estimates and selection wait LLM_ESTIMATE_TIMEOUT, not 420 s."""

    async def test_catalog_estimates_use_the_estimate_timeout(self, monkeypatch):
        from app.services import catalog_estimates

        monkeypatch.setattr(settings, "LLM_ESTIMATE_TIMEOUT", 123.0)
        with patch("app.services.catalog_estimates.httpx.AsyncClient") as client_class:
            _client_class_answering(client_class, "{}")
            await catalog_estimates._complete(
                [
                    catalog_estimates.EstimateRequest(
                        id="1", name="Milk", category="dairy"
                    )
                ]
            )

        assert client_class.call_args.kwargs["timeout"] == 123.0

    async def test_product_selection_uses_the_estimate_timeout(self, monkeypatch):
        from app.services import product_selection

        monkeypatch.setattr(settings, "LLM_ESTIMATE_TIMEOUT", 123.0)
        line = product_selection.SelectionLine(
            line_id="a",
            printed="MAITO",
            generic="Milk",
            category="dairy",
            candidate_ids=("00000000-0000-0000-0000-000000000001",),
            candidate_names=("Milk",),
        )
        with patch("app.services.product_selection.httpx.AsyncClient") as client_class:
            _client_class_answering(client_class, '{"r": []}')
            await product_selection.select_products([line])

        assert client_class.call_args.kwargs["timeout"] == 123.0

    async def test_the_receipt_read_keeps_llm_timeout(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_ESTIMATE_TIMEOUT", 123.0)
        with patch("app.services.llm_extractor.httpx.AsyncClient") as client_class:
            _client_class_answering(client_class, _compact())
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert client_class.call_args.kwargs["timeout"] == settings.LLM_TIMEOUT


class TestConfigurationErrors:
    """PR #131 F16: a non-ASCII API key failed the request before any response, and the
    error handler read the unbound response: an UnboundLocalError, not a clear message."""

    async def test_a_non_ascii_api_key_is_a_clear_configuration_error(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "LLM_API_KEY", "avain-öö")
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        real_client = httpx.AsyncClient

        def client(*_args, **kwargs):
            return real_client(transport=transport, timeout=kwargs.get("timeout"))

        with (
            patch("app.services.llm_extractor.httpx.AsyncClient", side_effect=client),
            pytest.raises(LLMExtractionError, match="LLM_API_KEY") as caught,
        ):
            await extract_from_text(RECEIPT_TEXT, CATEGORIES)

        assert caught.value.raw_completion is None
