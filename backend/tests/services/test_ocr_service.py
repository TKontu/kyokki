"""Tests for OCR service."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, mock_open

from app.services.ocr_service import (
    extract_text_from_receipt,
    _extract_from_pdf,
    _extract_from_image,
)


class TestExtractTextFromReceipt:
    """Tests for extract_text_from_receipt function."""

    async def test_routes_pdf_to_pdfplumber(self, tmp_path):
        """PDF files should be routed to pdfplumber."""
        pdf_file = tmp_path / "receipt.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        with patch("app.services.ocr_service._extract_from_pdf") as mock_pdf:
            mock_pdf.return_value = "PDF TEXT"

            result = await extract_text_from_receipt(str(pdf_file))

            assert result == "PDF TEXT"
            mock_pdf.assert_called_once()

    async def test_routes_jpg_to_mineru(self, tmp_path):
        """JPG files should be routed to MinerU."""
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"fake image")

        with patch("app.services.ocr_service._extract_from_image") as mock_img:
            mock_img.return_value = "IMAGE TEXT"

            result = await extract_text_from_receipt(str(img_file))

            assert result == "IMAGE TEXT"
            mock_img.assert_called_once()

    async def test_routes_png_to_mineru(self, tmp_path):
        """PNG files should be routed to MinerU."""
        img_file = tmp_path / "receipt.png"
        img_file.write_bytes(b"fake image")

        with patch("app.services.ocr_service._extract_from_image") as mock_img:
            mock_img.return_value = "PNG TEXT"

            result = await extract_text_from_receipt(str(img_file))

            assert result == "PNG TEXT"
            mock_img.assert_called_once()

    async def test_rejects_unsupported_file_types(self, tmp_path):
        """Unsupported file types should raise ValueError."""
        txt_file = tmp_path / "receipt.txt"
        txt_file.write_text("some text")

        with pytest.raises(ValueError, match="Unsupported file type"):
            await extract_text_from_receipt(str(txt_file))


class TestExtractFromPdf:
    """Tests for _extract_from_pdf function."""

    def test_extracts_text_from_single_page_pdf(self):
        """Should extract text from single page PDF."""
        mock_page = Mock()
        mock_page.extract_text.return_value = "Page 1 text"

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        with patch("app.services.ocr_service.pdfplumber.open", return_value=mock_pdf):
            result = _extract_from_pdf(Path("test.pdf"))

            assert result == "Page 1 text"

    def test_extracts_text_from_multi_page_pdf(self):
        """Should extract and join text from multiple pages."""
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page 1"

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page 2"

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        with patch("app.services.ocr_service.pdfplumber.open", return_value=mock_pdf):
            result = _extract_from_pdf(Path("test.pdf"))

            assert result == "Page 1\nPage 2"

    def test_handles_empty_pages(self):
        """Should handle pages with no text."""
        mock_page = Mock()
        mock_page.extract_text.return_value = None

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        with patch("app.services.ocr_service.pdfplumber.open", return_value=mock_pdf):
            result = _extract_from_pdf(Path("test.pdf"))

            assert result == ""


class TestExtractFromImage:
    """Tests for _extract_from_image function."""

    @pytest.mark.asyncio
    async def test_calls_mineru_api_with_correct_params(self, tmp_path):
        """Should call MinerU API with correct parameters."""
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"fake image data")

        mock_response = Mock()
        mock_response.json.return_value = {
            "results": {
                "receipt.jpg": {
                    "md_content": "Extracted text from MinerU"
                }
            }
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.services.ocr_service.httpx.AsyncClient", return_value=mock_client):
            result = await _extract_from_image(img_file)

            assert result == "Extracted text from MinerU"
            mock_client.post.assert_called_once()

            # Check that correct parameters were sent
            call_args = mock_client.post.call_args
            assert "file_parse" in call_args[0][0]  # URL contains /file_parse
            assert "data" in call_args[1]  # form_data passed as data
            assert "files" in call_args[1]  # file passed as files

    @pytest.mark.asyncio
    async def test_handles_empty_mineru_response(self, tmp_path):
        """Should return empty string if MinerU returns no results."""
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"fake image")

        mock_response = Mock()
        mock_response.json.return_value = {"results": {}}
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("app.services.ocr_service.httpx.AsyncClient", return_value=mock_client):
            result = await _extract_from_image(img_file)

            assert result == ""

    @pytest.mark.asyncio
    async def test_raises_on_mineru_http_error(self, tmp_path):
        """Should raise HTTPError if MinerU service fails."""
        import httpx

        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"fake image")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("API Error"))

        with patch("app.services.ocr_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPError):
                await _extract_from_image(img_file)


@pytest.mark.integration
class TestOCRWithRealSamples:
    """Integration tests with real sample files."""

    async def test_extract_from_s_group_pdf(self):
        """Integration test with real S-Group PDF sample."""
        # Samples mounted at /app/samples in Docker
        sample_pdf = Path("samples/s_group_receipt.pdf")

        if not sample_pdf.exists():
            pytest.skip(f"S-Group PDF sample not found at {sample_pdf}")

        text = await extract_text_from_receipt(str(sample_pdf))

        # Should extract text successfully
        assert len(text) > 0
        # Should contain S-Group markers
        assert any(marker in text.upper() for marker in ["PRISMA", "S-KAUPAT", "S-MARKET"])

    @pytest.mark.skip(reason="Requires MinerU service running")
    async def test_extract_from_kesko_image(self):
        """Integration test with real K-Group image sample.

        Skipped by default as it requires MinerU service to be running.
        Run with: pytest -m integration --run-mineru
        """
        sample_img = Path("samples/kesko_receipt.jpg")

        if not sample_img.exists():
            pytest.skip(f"Kesko image sample not found at {sample_img}")

        text = await _extract_from_image(sample_img)

        # Should extract text successfully
        assert len(text) > 0
        # Should contain K-Group markers
        assert any(marker in text.upper() for marker in ["K-MARKET", "K-CITYMARKET", "KESKO"])
