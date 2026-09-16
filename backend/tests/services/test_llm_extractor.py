"""Tests for the LLM receipt extractor (compact JSON contract proven in MVP-R0)."""

import base64
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.parsers.base import ExtractedLine, ReceiptExtraction
from app.services.llm_extractor import (
    MAX_KNOWN_PRODUCTS,
    CategoryOption,
    LLMExtractionError,
    build_instructions,
    build_response_schema,
    extract_from_image,
    extract_from_text,
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


def _compact(**overrides) -> str:
    body = {
        "s": "S-KAUPAT",
        "d": "2026-01-02",
        "p": [
            {
                "n": "KEVYTMAITOJUOMA LAKTON",
                "g": "Lactose-free milk",
                "q": 1,
                "w": None,
                "c": "dairy",
            },
            {"n": "PUNASIPULI", "g": "Red onion", "q": 1, "w": 0.33, "c": "produce"},
        ],
    }
    body.update(overrides)
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
    def test_drops_totals_payment_vat_discount_and_fee_lines(self):
        filtered = prefilter_receipt_text(RECEIPT_TEXT)
        for dropped in (
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
            assert dropped not in filtered, dropped

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
        assert item["properties"]["c"]["enum"] == ["dairy", "produce", None]
        assert item["properties"]["g"] == {"type": "string"}
        assert item["required"] == ["n", "g", "q", "w", "c"]
        assert schema["required"] == ["s", "d", "p"]


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
            ),
            ExtractedLine(
                name="PUNASIPULI",
                generic_name="Red onion",
                quantity=1,
                weight_kg=0.33,
                category="produce",
            ),
        ]

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

    def test_list_known_products_to_reuse_their_names(self):
        text = build_instructions(CATEGORIES, ["Milk", "Ground beef", "milk"])
        assert "Known products: Ground beef, Milk." in text

    def test_without_known_products_the_list_is_omitted(self):
        assert "Known products" not in build_instructions(CATEGORIES)

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
        content = _compact(p=[{"n": "SIENILIINA", "q": 2, "w": None, "c": "household"}])
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
        assert "YHTEENSÄ" not in prompt
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
