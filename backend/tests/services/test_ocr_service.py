"""Tests for OCR service."""

from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import anyio
import httpx
import pytest
from PIL import Image

from app.services.ocr_service import (
    OCRUnavailableError,
    _extract_from_image,
    _extract_from_pdf,
    extract_text_from_receipt,
)


def _mineru_client(text: str) -> AsyncMock:
    """An httpx.AsyncClient stand-in whose POST answers like MinerU's /file_parse."""
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = {"results": {"receipt": {"md_content": text}}}
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)
    return client


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
            "results": {"receipt.jpg": {"md_content": "Extracted text from MinerU"}}
        }
        mock_response.raise_for_status = Mock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
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

        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
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

        with (
            patch(
                "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
            ),
            pytest.raises(httpx.HTTPError),
        ):
            await _extract_from_image(img_file)

    @pytest.mark.asyncio
    async def test_upscales_a_small_image_before_sending(self, tmp_path):
        """A Telegram-compressed photo is 289 px wide; OCR needs it enlarged.

        The 3x factor is the one measured on the deployed Lidl receipt: the same
        image that OCR turned into gibberish came back readable at 867 px.
        """
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (289, 1280), "white").save(img_file, format="JPEG")

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            assert await _extract_from_image(img_file) == "text"

        _, payload, content_type = mock_client.post.call_args.kwargs["files"]["files"]
        sent = Image.open(BytesIO(payload))
        assert (sent.width, sent.height) == (867, 3840)
        assert content_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_leaves_a_large_image_untouched(self, tmp_path):
        """Re-encoding a photo that is already wide enough would only lose detail."""
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (1200, 2000), "white").save(img_file, format="JPEG")
        original = img_file.read_bytes()

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, content_type = mock_client.post.call_args.kwargs["files"]["files"]
        assert payload == original
        assert content_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_reads_exif_orientation_before_measuring(self, tmp_path):
        """A rotated long receipt is 289 px wide on screen, whatever the stored size."""
        img_file = tmp_path / "receipt.jpg"
        stored = Image.new("RGB", (1280, 289), "white")
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 degrees clockwise for display
        stored.save(img_file, format="JPEG", exif=exif)

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        sent = Image.open(BytesIO(payload))
        assert (sent.width, sent.height) == (867, 3840)

    @pytest.mark.asyncio
    async def test_a_small_factor_is_not_worth_a_re_encode(self, tmp_path):
        """999 px must not become 1998 px just because it is a pixel under the threshold."""
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (999, 1400), "white").save(img_file, format="JPEG")
        original = img_file.read_bytes()

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        assert payload == original

    @pytest.mark.asyncio
    async def test_enlarges_to_the_threshold_not_the_next_power(self, tmp_path):
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (800, 1200), "white").save(img_file, format="JPEG")

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        sent = Image.open(BytesIO(payload))
        assert (sent.width, sent.height) == (1000, 1500)

    @pytest.mark.asyncio
    async def test_a_decompression_bomb_is_sent_untouched(self, tmp_path, monkeypatch):
        """A 200 MP photo used to reach MinerU; enlargement must not fail the receipt."""
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (20, 20), "white").save(img_file, format="JPEG")
        original = img_file.read_bytes()
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, content_type = mock_client.post.call_args.kwargs["files"]["files"]
        assert payload == original
        assert content_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_a_resize_over_the_pixel_cap_is_skipped(self, tmp_path, monkeypatch):
        """A long screenshot must not be enlarged to hundreds of megapixels."""
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (400, 800), "white").save(img_file, format="JPEG")
        original = img_file.read_bytes()
        monkeypatch.setattr("app.services.ocr_service.MAX_UPSCALED_PIXELS", 200_000)

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        assert payload == original

    @pytest.mark.asyncio
    async def test_zero_disables_the_enlargement(self, tmp_path, monkeypatch):
        from app.core.config import settings

        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (289, 1280), "white").save(img_file, format="JPEG")
        original = img_file.read_bytes()
        monkeypatch.setattr(settings, "MINERU_UPSCALE_BELOW_WIDTH", 0)

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        assert payload == original

    @pytest.mark.asyncio
    async def test_a_transparent_export_is_flattened_onto_white(self, tmp_path):
        """Transparent pixels stored as black must not turn the page black."""
        img_file = tmp_path / "receipt.png"
        image = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
        image.paste((0, 0, 0, 255), (0, 0, 400, 20))  # a line of black text
        image.save(img_file, format="PNG")

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        sent = Image.open(BytesIO(payload))
        assert sent.getpixel((0, 400)) == (255, 255, 255)
        assert sent.getpixel((0, 10))[0] < 60

    @pytest.mark.asyncio
    async def test_an_encode_failure_is_sent_untouched(self, tmp_path, monkeypatch):
        """A JPEG encoder failure must not fail the receipt either."""
        img_file = tmp_path / "receipt.jpg"
        Image.new("RGB", (400, 800), "white").save(img_file, format="JPEG")
        original = img_file.read_bytes()

        def boom(self, *args, **kwargs):
            raise OSError("encoder error -2")

        monkeypatch.setattr(Image.Image, "save", boom)
        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        _, payload, _ = mock_client.post.call_args.kwargs["files"]["files"]
        assert payload == original

    @pytest.mark.asyncio
    async def test_a_narrow_png_is_uploaded_as_jpeg_under_a_jpeg_name(self, tmp_path):
        """The part must not say .png while carrying JPEG bytes."""
        img_file = tmp_path / "receipt.png"
        Image.new("RGB", (400, 800), "white").save(img_file, format="PNG")

        mock_client = _mineru_client("text")
        with patch(
            "app.services.ocr_service.httpx.AsyncClient", return_value=mock_client
        ):
            await _extract_from_image(img_file)

        name, payload, content_type = mock_client.post.call_args.kwargs["files"][
            "files"
        ]
        assert (name, content_type) == ("receipt.jpg", "image/jpeg")
        assert payload[:3] == b"\xff\xd8\xff"


@pytest.mark.integration
class TestOCRWithRealSamples:
    """Integration tests with real sample files."""

    async def test_extract_from_s_group_pdf(self):
        """Integration test with real S-Group PDF sample."""
        sample_pdf = anyio.Path("samples/s_group_receipt.pdf")

        if not await sample_pdf.exists():
            pytest.skip(f"S-Group PDF sample not found at {sample_pdf}")

        text = await extract_text_from_receipt(str(sample_pdf))

        assert len(text) > 0
        assert any(
            marker in text.upper() for marker in ["PRISMA", "S-KAUPAT", "S-MARKET"]
        )

    @pytest.mark.requires_mineru
    async def test_extract_from_kesko_image(self):
        """Integration test with real K-Group image sample.

        Deselected by default (pytest.ini), because it calls MinerU for real. Run
        it with `pytest -m requires_mineru` when the service is up.
        """
        sample_img = anyio.Path("samples/kesko_receipt.jpg")

        if not await sample_img.exists():
            pytest.skip(f"Kesko image sample not found at {sample_img}")

        text = await _extract_from_image(sample_img)

        assert len(text) > 0
        assert any(
            marker in text.upper() for marker in ["K-MARKET", "K-CITYMARKET", "KESKO"]
        )


class TestMinerURequestAndAvailability:
    """MVP-R1a: configurable language, real content type, availability errors."""

    @staticmethod
    def _client(post):
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = post
        return client

    async def test_sends_configured_language_and_real_content_type(
        self, tmp_path, monkeypatch
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "MINERU_LANG", "latin")
        img_file = tmp_path / "receipt.png"
        img_file.write_bytes(b"\x89PNG fake")
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {
            "results": {"receipt.png": {"md_content": "TEXT"}}
        }
        post = AsyncMock(return_value=response)

        with patch(
            "app.services.ocr_service.httpx.AsyncClient",
            return_value=self._client(post),
        ) as client_cls:
            assert await _extract_from_image(img_file) == "TEXT"

        assert post.call_args.kwargs["data"]["lang_list"] == "latin"
        name, _, content_type = post.call_args.kwargs["files"]["files"]
        assert (name, content_type) == ("receipt.png", "image/png")
        assert client_cls.call_args.kwargs["timeout"] == settings.MINERU_TIMEOUT

    @pytest.mark.parametrize(
        "error",
        [
            httpx.ConnectError("refused"),
            httpx.ReadTimeout("slow"),
        ],
    )
    async def test_connection_problems_raise_unavailable(self, tmp_path, error):
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"fake")
        post = AsyncMock(side_effect=error)

        with (
            patch(
                "app.services.ocr_service.httpx.AsyncClient",
                return_value=self._client(post),
            ),
            pytest.raises(OCRUnavailableError),
        ):
            await _extract_from_image(img_file)

    async def test_server_error_raises_unavailable(self, tmp_path):
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"fake")
        request = httpx.Request("POST", "http://mineru/file_parse")
        response = Mock()
        response.status_code = 503
        response.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "down", request=request, response=httpx.Response(503, request=request)
            )
        )
        post = AsyncMock(return_value=response)

        with (
            patch(
                "app.services.ocr_service.httpx.AsyncClient",
                return_value=self._client(post),
            ),
            pytest.raises(OCRUnavailableError),
        ):
            await _extract_from_image(img_file)
