"""OCR service for receipt text extraction.

Routes between pdfplumber (digital PDFs) and MinerU (photo receipts). When MinerU cannot be
reached, ``OCRUnavailableError`` lets the pipeline read the image with a vision model instead.
"""

import asyncio
import mimetypes
from pathlib import Path

import httpx
import pdfplumber

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class OCRUnavailableError(Exception):
    """The OCR service could not be reached, timed out, or failed on its side (5xx)."""


def is_pdf(file_path: str | Path) -> bool:
    return Path(file_path).suffix.lower() == ".pdf"


def content_type_for(file_path: str | Path) -> str:
    """MIME type from the file name, e.g. image/png; octet-stream when unknown."""
    guessed, _ = mimetypes.guess_type(str(file_path))
    return guessed or "application/octet-stream"


async def extract_text_from_receipt(file_path: str) -> str:
    """Extract text from receipt image or PDF.

    Routes:
    - PDF files → pdfplumber (for digital receipts like S-Group PDFs)
    - Image files → MinerU OCR service (for photo receipts)

    Raises:
        ValueError: If file type unsupported.
        OCRUnavailableError: If MinerU cannot be reached or fails on its side.
        httpx.HTTPError: For other MinerU request failures.
    """
    path = Path(file_path)

    if is_pdf(path):
        logger.info("Extracting text from PDF", extra={"file": path.name})
        return await asyncio.to_thread(_extract_from_pdf, path)
    if path.suffix.lower() in IMAGE_SUFFIXES:
        logger.info("Extracting text from image via MinerU", extra={"file": path.name})
        return await _extract_from_image(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def _extract_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber (blocking; run it in a thread)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(pages_text)
            logger.debug(f"Extracted {len(text)} chars from {len(pdf.pages)} pages")
            return text
    except Exception as e:
        logger.error(f"PDF extraction failed for {pdf_path}: {e}")
        raise


async def _extract_from_image(image_path: Path) -> str:
    """Extract text from an image with the self-hosted MinerU FastAPI endpoint.

    Returns:
        Extracted markdown text ("" when MinerU finds nothing).

    Raises:
        OCRUnavailableError: Connection failure, timeout, or a 5xx response.
        httpx.HTTPError: Other request failures (4xx).
    """
    url = f"{settings.MINERU_BASE_URL}/file_parse"

    form_data = {
        "backend": "pipeline",  # OCR pipeline (not VLM)
        "lang_list": settings.MINERU_LANG,
        "formula_enable": str(settings.MINERU_ENABLE_FORMULA).lower(),
        "table_enable": str(settings.MINERU_ENABLE_TABLE).lower(),
        "return_md": "true",
        "return_content_list": "false",
        "return_model_output": "false",
        "return_middle_json": "false",
        "return_images": "false",
        "response_format_zip": "false",
        "start_page_id": "0",
        "end_page_id": "99999",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.MINERU_TIMEOUT) as client:
            with open(image_path, "rb") as f:  # noqa: ASYNC230
                files = {"files": (image_path.name, f, content_type_for(image_path))}
                logger.debug(f"Sending {image_path.name} to MinerU at {url}")
                response = await client.post(url, data=form_data, files=files)
                response.raise_for_status()

            json_resp = response.json()
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning("MinerU unreachable", extra={"error": repr(e)})
        raise OCRUnavailableError(f"MinerU unreachable: {e!r}") from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code >= 500:
            logger.warning(
                "MinerU server error", extra={"status": e.response.status_code}
            )
            raise OCRUnavailableError(
                f"MinerU returned {e.response.status_code}"
            ) from e
        logger.error(f"MinerU API request failed for {image_path}: {e}")
        raise
    except httpx.HTTPError as e:
        logger.error(f"MinerU API request failed for {image_path}: {e}")
        raise

    # Response structure: {"results": {"<filename>": {"md_content": "..."}}}
    results = json_resp.get("results", {})
    if not results:
        logger.warning("MinerU returned empty results")
        return ""

    doc_data = results[next(iter(results))]
    markdown_text = str(doc_data.get("md_content") or "")
    logger.info(f"Extracted {len(markdown_text)} chars from MinerU OCR")
    return markdown_text
