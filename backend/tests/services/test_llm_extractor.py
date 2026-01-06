"""Pytest tests for LLM extractor service (vLLM integration)."""
import json
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.services.llm_extractor import (
    extract_products_from_receipt,
    extract_with_store_hint,
    build_prompt_for_store,
)
from app.parsers.base import ReceiptExtraction, ParsedProduct, StoreInfo
from app.core.config import settings


class TestExtractProductsFromReceipt:
    """Test LLM extraction with vLLM structured output."""

    @pytest.fixture
    def mock_vllm_response(self):
        """Mock successful vLLM API response."""
        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "qwen3-8B",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({
                            "store": {
                                "name": "Prisma Jyväskylä",
                                "chain": "s-group",
                                "country": "FI",
                                "language": "fi",
                                "currency": "EUR"
                            },
                            "products": [
                                {
                                    "name": "Maito",
                                    "name_en": "Milk",
                                    "quantity": 1.0,
                                    "weight_kg": None,
                                    "volume_l": 1.0,
                                    "unit": "l",
                                    "price": 1.49
                                },
                                {
                                    "name": "Leipä",
                                    "name_en": "Bread",
                                    "quantity": 1.0,
                                    "weight_kg": None,
                                    "volume_l": None,
                                    "unit": "pcs",
                                    "price": 2.95
                                }
                            ],
                            "confidence": 0.95
                        })
                    },
                    "finish_reason": "stop"
                }
            ]
        }

    @pytest.fixture
    def sample_ocr_text(self):
        """Sample Finnish S-Group receipt OCR text."""
        return """
        PRISMA JYVÄSKYLÄ
        S-KAUPAT OY

        Maito 1 l            1.49
        Leipä                2.95

        YHTEENSÄ            4.44
        KORTTI              4.44
        """

    async def test_successful_extraction(self, mock_vllm_response, sample_ocr_text):
        """Test successful product extraction with valid vLLM response."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock the response object
            mock_response = AsyncMock()
            mock_response.json = lambda: mock_vllm_response  # Sync method
            mock_response.raise_for_status = lambda: None  # Sync method

            # Mock the post method
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            # Execute extraction
            result = await extract_products_from_receipt(sample_ocr_text)

            # Verify result
            assert isinstance(result, ReceiptExtraction)
            assert len(result.products) == 2
            assert result.get_store_info().name == "Prisma Jyväskylä"
            assert result.get_store_info().chain == "s-group"
            assert result.get_store_info().country == "FI"
            assert result.confidence == 0.95

            # Verify first product
            product1 = result.products[0]
            assert product1.name == "Maito"
            assert product1.name_en == "Milk"
            assert product1.volume_l == 1.0
            assert product1.unit == "l"
            assert product1.price == 1.49

            # Verify second product
            product2 = result.products[1]
            assert product2.name == "Leipä"
            assert product2.name_en == "Bread"
            assert product2.unit == "pcs"
            assert product2.price == 2.95

            # Verify API call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]

            assert payload["model"] == settings.LLM_MODEL
            assert payload["temperature"] == settings.LLM_TEMPERATURE
            assert payload["max_tokens"] == 16384
            # Note: response_format is NOT included because it causes thinking loops in vLLM
            # The prompt itself instructs the model to output JSON
            assert "response_format" not in payload

    async def test_extraction_with_minimal_response(self):
        """Test extraction with minimal valid response (no store info)."""
        minimal_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "store": {},
                            "products": [
                                {
                                    "name": "Product",
                                    "quantity": 1.0,
                                    "unit": "pcs"
                                }
                            ]
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = lambda: minimal_response
            mock_response.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await extract_products_from_receipt("Some OCR text")

            assert isinstance(result, ReceiptExtraction)
            assert len(result.products) == 1
            assert result.products[0].name == "Product"
            assert result.get_store_info().name is None

    async def test_http_error_handling(self, sample_ocr_text):
        """Test handling of vLLM API HTTP errors."""
        with patch("httpx.AsyncClient") as mock_client:
            # Create mock request and response for HTTPStatusError
            mock_request = AsyncMock()
            mock_error_response = AsyncMock()
            mock_error_response.status_code = 500

            def raise_status_error():
                raise httpx.HTTPStatusError(
                    "500 Server Error",
                    request=mock_request,
                    response=mock_error_response
                )

            mock_response = AsyncMock()
            mock_response.raise_for_status = raise_status_error

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            with pytest.raises(httpx.HTTPStatusError):
                await extract_products_from_receipt(sample_ocr_text)

    async def test_invalid_json_response(self, sample_ocr_text):
        """Test handling of invalid JSON in response."""
        invalid_response = {
            "choices": [
                {
                    "message": {
                        "content": "not valid json"
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = lambda: invalid_response
            mock_response.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            with pytest.raises(Exception):  # Pydantic validation error
                await extract_products_from_receipt(sample_ocr_text)

    async def test_ocr_text_truncation(self):
        """Test that OCR text is truncated to 4000 characters."""
        long_text = "A" * 5000

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = lambda: {
                "choices": [{"message": {"content": json.dumps({"store": {}, "products": []})}}]
            }
            mock_response.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            await extract_products_from_receipt(long_text)

            # Verify OCR text was truncated to 4000 chars
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            prompt = payload["messages"][0]["content"]

            # Check that "AAAA..." appears in prompt but not all 5000 As
            # OCR text should be limited to 4000 chars (prompt template adds overhead)
            assert "A" * 4000 in prompt  # Truncated text is present
            assert "A" * 4001 not in prompt  # But not more than 4000 chars


class TestBuildPromptForStore:
    """Test prompt building with store hints."""

    def test_basic_prompt_without_hint(self):
        """Test basic prompt generation without store hint."""
        prompt = build_prompt_for_store("Sample OCR text")

        assert "Sample OCR text" in prompt
        assert "language-agnostic" in prompt.lower() or "any language" in prompt.lower()
        assert "Note: This receipt appears to be from" not in prompt

    def test_prompt_with_store_hint(self):
        """Test prompt includes store hint."""
        prompt = build_prompt_for_store("Sample OCR text", "Prisma")

        assert "Sample OCR text" in prompt
        assert "Prisma" in prompt
        assert "Note: This receipt appears to be from Prisma" in prompt

    def test_prompt_truncation(self):
        """Test OCR text is truncated in prompt."""
        long_text = "X" * 5000
        prompt = build_prompt_for_store(long_text)

        # Should contain truncated text (max 4000 chars)
        assert "X" * 4000 in prompt
        # Prompt should be truncated: 4000 char text + ~2000 char template = ~6000 chars
        assert len(prompt) < 7000  # Allow for template overhead
        assert len(prompt) > 5000  # Should have text + template


class TestExtractWithStoreHint:
    """Test LLM extraction with store hint."""

    @pytest.fixture
    def mock_vllm_response(self):
        """Mock vLLM response with store hint applied."""
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "store": {
                                "name": "Prisma",
                                "chain": "s-group",
                                "country": "FI",
                                "language": "fi",
                                "currency": "EUR"
                            },
                            "products": [
                                {
                                    "name": "Test Product",
                                    "quantity": 1.0,
                                    "unit": "pcs"
                                }
                            ]
                        })
                    }
                }
            ]
        }

    async def test_extraction_with_hint(self, mock_vllm_response):
        """Test extraction includes store hint in prompt."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = lambda: mock_vllm_response
            mock_response.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await extract_with_store_hint("Sample OCR", "Prisma")

            assert isinstance(result, ReceiptExtraction)
            assert len(result.products) == 1
            assert result.get_store_info().name == "Prisma"

            # Verify prompt included hint
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            prompt = payload["messages"][0]["content"]

            assert "Prisma" in prompt
            assert "Note: This receipt appears to be from Prisma" in prompt

    async def test_http_error_with_hint(self):
        """Test error handling with store hint."""
        with patch("httpx.AsyncClient") as mock_client:
            # Create mock request and response for HTTPStatusError
            mock_request = AsyncMock()
            mock_error_response = AsyncMock()
            mock_error_response.status_code = 503

            def raise_status_error():
                raise httpx.HTTPStatusError(
                    "503 Service Unavailable",
                    request=mock_request,
                    response=mock_error_response
                )

            mock_response = AsyncMock()
            mock_response.raise_for_status = raise_status_error

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            with pytest.raises(httpx.HTTPStatusError):
                await extract_with_store_hint("OCR text", "K-Citymarket")


class TestLanguageAgnosticExtraction:
    """Test language-agnostic extraction capabilities."""

    @pytest.mark.parametrize("language,store_name,product_names", [
        ("fi", "Prisma", ["Maito", "Leipä"]),
        ("en", "Walmart", ["Milk", "Bread"]),
        ("de", "LIDL", ["Milch", "Brot"]),
        ("sv", "ICA", ["Mjölk", "Bröd"]),
    ])
    async def test_multi_language_extraction(self, language, store_name, product_names):
        """Test extraction works with different languages."""
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "store": {
                                "name": store_name,
                                "language": language,
                                "country": "FI" if language == "fi" else "US"
                            },
                            "products": [
                                {"name": name, "quantity": 1.0, "unit": "pcs"}
                                for name in product_names
                            ]
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = AsyncMock()
            mock_resp.json = lambda: mock_response
            mock_resp.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_resp)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await extract_products_from_receipt(f"{store_name} receipt text")

            assert result.get_store_info().language == language
            assert len(result.products) == len(product_names)
            for i, product in enumerate(result.products):
                assert product.name == product_names[i]


class TestPydanticValidation:
    """Test Pydantic model validation of LLM responses."""

    async def test_invalid_product_schema(self):
        """Test that invalid product schema raises validation error."""
        invalid_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "store": {},
                            "products": [
                                {
                                    "name": "Product",
                                    "quantity": -1.0,  # Invalid: negative quantity
                                    "unit": "pcs"
                                }
                            ]
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = lambda: invalid_response
            mock_response.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            with pytest.raises(Exception):  # Pydantic validation error
                await extract_products_from_receipt("OCR text")

    async def test_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        invalid_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "store": {},
                            "products": [
                                {
                                    # Missing 'name' field
                                    "quantity": 1.0,
                                    "unit": "pcs"
                                }
                            ]
                        })
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json = lambda: invalid_response
            mock_response.raise_for_status = lambda: None

            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post

            with pytest.raises(Exception):  # Pydantic validation error
                await extract_products_from_receipt("OCR text")
