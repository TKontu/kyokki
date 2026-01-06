"""Live integration tests for external services (vLLM and MinerU).

These tests make REAL API calls to external services and are skipped by default.

To run vLLM tests:
    pytest tests/services/test_live_services.py -m requires_vllm -v

To run MinerU tests:
    pytest tests/services/test_live_services.py -m requires_mineru -v

To run all live service tests:
    pytest tests/services/test_live_services.py -m "requires_vllm or requires_mineru" -v
"""
import pytest
from pathlib import Path

from app.services.llm_extractor import extract_products_from_receipt, extract_with_store_hint
from app.services.ocr_service import extract_text_from_receipt
from app.parsers.base import ReceiptExtraction
from app.core.config import settings


class TestLiveVLLMService:
    """Integration tests with real vLLM service at 192.168.0.247:9003."""

    @pytest.mark.requires_vllm
    async def test_vllm_extraction_with_simple_receipt(self):
        """Test actual vLLM extraction with a simple synthetic receipt."""
        sample_receipt = """
        PRISMA JYVÄSKYLÄ
        S-KAUPAT OY

        Maito 1 l                   1.49
        Ruisleipä                   2.95
        Juusto 400g                 4.50

        YHTEENSÄ                    8.94
        KORTTI                      8.94

        Kiitos käynnistä!
        """

        result = await extract_products_from_receipt(sample_receipt)

        # Verify response structure
        assert isinstance(result, ReceiptExtraction)
        assert result.products is not None

        # Should extract at least some products
        assert len(result.products) >= 1, "vLLM should extract at least one product"

        # Verify store detection (may or may not work depending on LLM)
        store_info = result.get_store_info()
        print(f"\nExtracted store: {store_info.name}, chain: {store_info.chain}")
        print(f"Extracted {len(result.products)} products:")
        for i, product in enumerate(result.products, 1):
            print(f"  {i}. {product.name} ({product.name_en}) - {product.quantity} {product.unit}")

    @pytest.mark.requires_vllm
    async def test_vllm_extraction_with_english_receipt(self):
        """Test vLLM with English receipt to verify language-agnostic capability."""
        sample_receipt = """
        WALMART SUPERCENTER
        123 Main Street

        Milk 1 gal                  $3.49
        Bread                       $2.50
        Eggs 12ct                   $4.99

        TOTAL                      $10.98
        VISA                       $10.98
        """

        result = await extract_products_from_receipt(sample_receipt)

        assert isinstance(result, ReceiptExtraction)
        assert len(result.products) >= 1

        store_info = result.get_store_info()
        print(f"\nExtracted store: {store_info.name}")
        print(f"Language: {store_info.language}, Country: {store_info.country}")
        print(f"Currency: {store_info.currency}")

        # Verify at least one product name
        assert any(p.name for p in result.products), "Should extract product names"

    @pytest.mark.requires_vllm
    async def test_vllm_extraction_with_store_hint(self):
        """Test vLLM extraction with store hint for improved accuracy."""
        sample_receipt = """
        PRISMA

        Maito                       1.49
        Leipä                       2.95
        """

        result = await extract_with_store_hint(sample_receipt, "Prisma (S-Group)")

        assert isinstance(result, ReceiptExtraction)
        assert len(result.products) >= 1

        store_info = result.get_store_info()
        print(f"\nWith hint 'Prisma (S-Group)':")
        print(f"Detected: {store_info.name}, chain: {store_info.chain}")

    @pytest.mark.requires_vllm
    async def test_vllm_model_configuration(self):
        """Verify vLLM is using the correct model (Qwen3-4B-Instruct)."""
        import httpx

        # This test verifies the model name is correctly configured
        # Actual model verification would require vLLM API /models endpoint
        assert settings.LLM_MODEL == "Qwen3-4B-Instruct", "Should be configured to use Qwen3-4B-Instruct"
        assert settings.LLM_BASE_URL == "http://192.168.0.247:9003/v1"

        print(f"\nConfigured model: {settings.LLM_MODEL}")
        print(f"Base URL: {settings.LLM_BASE_URL}")
        print(f"Temperature: {settings.LLM_TEMPERATURE}")


class TestLiveMinerUService:
    """Integration tests with real MinerU OCR service at 192.168.0.136:8000."""

    @pytest.mark.requires_mineru
    async def test_mineru_ocr_with_real_image(self, tmp_path):
        """Test MinerU OCR with a real image file.

        Note: This test requires a sample image file in samples/ directory.
        If no sample exists, the test will be skipped.
        """
        # Check if sample image exists
        sample_image = Path("samples/kesko_receipt.jpg")
        if not sample_image.exists():
            pytest.skip(f"Sample image not found at {sample_image}")

        # Extract OCR text
        ocr_text = await extract_text_from_receipt(str(sample_image))

        # Verify we got some text
        assert ocr_text, "MinerU should return OCR text"
        assert len(ocr_text) > 10, "OCR text should be substantial"

        print(f"\nExtracted {len(ocr_text)} characters from image")
        print(f"First 200 chars: {ocr_text[:200]}")

    @pytest.mark.requires_mineru
    async def test_mineru_with_pdf_fallback(self):
        """Test that PDFs use pdfplumber, not MinerU."""
        sample_pdf = Path("samples/s_group_receipt.pdf")
        if not sample_pdf.exists():
            pytest.skip(f"Sample PDF not found at {sample_pdf}")

        # This should use pdfplumber, not MinerU
        ocr_text = await extract_text_from_receipt(str(sample_pdf))

        assert ocr_text, "Should extract text from PDF"
        assert len(ocr_text) > 10

        # Verify it looks like Finnish S-Group receipt
        text_upper = ocr_text.upper()
        assert any(marker in text_upper for marker in ["PRISMA", "S-KAUPAT", "S-MARKET"]), \
            "Should contain S-Group store markers"

        print(f"\nExtracted {len(ocr_text)} characters from PDF")


class TestLiveEndToEndPipeline:
    """End-to-end integration tests combining OCR and LLM extraction."""

    @pytest.mark.requires_mineru
    @pytest.mark.requires_vllm
    async def test_end_to_end_ocr_and_extraction_with_pdf(self):
        """Full pipeline: PDF → pdfplumber → vLLM → structured data."""
        sample_pdf = Path("samples/s_group_receipt.pdf")
        if not sample_pdf.exists():
            pytest.skip(f"Sample PDF not found at {sample_pdf}")

        # Step 1: OCR
        print("\n=== Step 1: OCR Extraction ===")
        ocr_text = await extract_text_from_receipt(str(sample_pdf))
        print(f"Extracted {len(ocr_text)} characters")

        # Step 2: LLM Extraction
        print("\n=== Step 2: LLM Product Extraction ===")
        result = await extract_products_from_receipt(ocr_text)

        # Verify results
        assert isinstance(result, ReceiptExtraction)
        assert len(result.products) >= 1, "Should extract at least one product from real receipt"

        store_info = result.get_store_info()
        print(f"\nStore: {store_info.name}")
        print(f"Chain: {store_info.chain}")
        print(f"Country: {store_info.country}, Language: {store_info.language}")
        print(f"\nExtracted {len(result.products)} products:")

        for i, product in enumerate(result.products, 1):
            print(f"  {i}. {product.name}")
            if product.name_en:
                print(f"     English: {product.name_en}")
            print(f"     Quantity: {product.quantity} {product.unit}")
            if product.price:
                print(f"     Price: {product.price}")

        # Verify at least one product has a name
        assert any(p.name for p in result.products)

    @pytest.mark.requires_mineru
    @pytest.mark.requires_vllm
    async def test_end_to_end_ocr_and_extraction_with_image(self):
        """Full pipeline: Image → MinerU → vLLM → structured data."""
        sample_image = Path("samples/kesko_receipt.jpg")
        if not sample_image.exists():
            pytest.skip(f"Sample image not found at {sample_image}")

        # Step 1: OCR with MinerU
        print("\n=== Step 1: MinerU OCR ===")
        ocr_text = await extract_text_from_receipt(str(sample_image))
        print(f"Extracted {len(ocr_text)} characters")

        # Step 2: LLM Extraction
        print("\n=== Step 2: vLLM Product Extraction ===")
        result = await extract_products_from_receipt(ocr_text)

        # Verify results
        assert isinstance(result, ReceiptExtraction)

        store_info = result.get_store_info()
        print(f"\nStore: {store_info.name}")
        print(f"Chain: {store_info.chain}")
        print(f"Extracted {len(result.products)} products")

        # May extract 0 products if image quality is poor or OCR fails
        # So we just verify the structure is correct
        assert result.products is not None
