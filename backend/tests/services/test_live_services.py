"""Live integration tests for external services (LLM gateway and MinerU).

These tests make REAL API calls and are deselected by default (see pytest.ini).

    pytest tests/services/test_live_services.py -m requires_vllm -v
    pytest tests/services/test_live_services.py -m requires_mineru -v

The LLM tests use the configured gateway and model (llama-swap `muse-glimmer` by default).
Each extraction call takes tens of seconds because the model always reasons.
"""

import anyio
import pytest

from app.core.config import settings
from app.parsers.base import ReceiptExtraction
from app.services.llm_extractor import CategoryOption, extract_from_text
from app.services.ocr_service import extract_text_from_receipt

CATEGORIES = [
    CategoryOption(id="dairy", name="Dairy & Eggs"),
    CategoryOption(id="bread", name="Bread & Bakery"),
    CategoryOption(id="cheese", name="Cheese"),
]


class TestLiveLLMGateway:
    """Integration tests against the real OpenAI-compatible gateway."""

    @pytest.mark.requires_vllm
    async def test_extracts_a_short_finnish_receipt(self):
        receipt = """PRISMA JYVÄSKYLÄ
S-KAUPAT OY
02.01.2026 11:40
MAITO 1 L                   1,49
RUISLEIPÄ                   2,95
JUUSTO 400G                 4,50
2 KPL 2,25 €/KPL
YHTEENSÄ                    8,94
KORTTI                      8,94
"""
        result = await extract_from_text(receipt, CATEGORIES)

        assert isinstance(result, ReceiptExtraction)
        assert result.method == "text"
        names = [line.name.upper() for line in result.lines]
        assert any("MAITO" in name for name in names)
        assert any("RUISLEIPÄ" in name for name in names)
        cheese = next(line for line in result.lines if "JUUSTO" in line.name.upper())
        assert cheese.quantity == 2
        assert not any("YHTEENSÄ" in name for name in names)
        assert result.purchase_date is not None

    @pytest.mark.requires_vllm
    async def test_model_configuration(self):
        assert settings.LLM_BASE_URL.endswith("/v1")
        assert settings.LLM_MODEL
        assert settings.LLM_MAX_TOKENS >= 2048


class TestLiveMinerUService:
    """Integration tests with the real MinerU OCR service."""

    @pytest.mark.requires_mineru
    async def test_mineru_ocr_with_real_image(self):
        sample_image = anyio.Path("samples/kesko_receipt.jpg")
        if not await sample_image.exists():
            pytest.skip(f"Sample image not found at {sample_image}")

        ocr_text = await extract_text_from_receipt(str(sample_image))

        assert ocr_text, "MinerU should return OCR text"
        assert len(ocr_text) > 10, "OCR text should be substantial"

    @pytest.mark.requires_mineru
    async def test_pdf_uses_pdfplumber(self):
        sample_pdf = anyio.Path("samples/s_group_receipt.pdf")
        if not await sample_pdf.exists():
            pytest.skip(f"Sample PDF not found at {sample_pdf}")

        ocr_text = await extract_text_from_receipt(str(sample_pdf))

        assert any(
            marker in ocr_text.upper() for marker in ["PRISMA", "S-KAUPAT", "S-MARKET"]
        )


class TestLiveEndToEndPipeline:
    """OCR plus extraction against both real services."""

    @pytest.mark.requires_mineru
    @pytest.mark.requires_vllm
    async def test_pdf_to_lines(self):
        sample_pdf = anyio.Path("samples/s_group_receipt.pdf")
        if not await sample_pdf.exists():
            pytest.skip(f"Sample PDF not found at {sample_pdf}")

        ocr_text = await extract_text_from_receipt(str(sample_pdf))
        result = await extract_from_text(ocr_text, CATEGORIES)

        assert len(result.lines) >= 1
