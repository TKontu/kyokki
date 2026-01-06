"""OCR service for receipt text extraction.

Routes between pdfplumber (digital PDFs) and MinerU (photo receipts).
Based on reference implementation in samples/mineru_selfhosted.py.
"""
import httpx
import pdfplumber
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def extract_text_from_receipt(file_path: str) -> str:
    """Extract text from receipt image or PDF.

    Routes:
    - PDF files → pdfplumber (for digital receipts like S-Group PDFs)
    - Image files → MinerU OCR service (for photo receipts)

    Args:
        file_path: Path to receipt file.

    Returns:
        Extracted text as string.

    Raises:
        ValueError: If file type unsupported.
        httpx.HTTPError: If MinerU service fails.
    """
    path = Path(file_path)

    if path.suffix.lower() == ".pdf":
        logger.info(f"Extracting text from PDF: {path.name}")
        return _extract_from_pdf(path)
    elif path.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"]:
        logger.info(f"Extracting text from image via MinerU: {path.name}")
        return await _extract_from_image(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")


def _extract_from_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber.

    Args:
        pdf_path: Path to PDF file.

    Returns:
        Extracted text from all pages.
    """
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
    """Extract text from image using MinerU OCR service.

    Based on reference implementation in samples/mineru_selfhosted.py.
    Uses the self-hosted MinerU FastAPI endpoint.

    Args:
        image_path: Path to image file.

    Returns:
        Extracted markdown text from MinerU.

    Raises:
        httpx.HTTPError: If MinerU service request fails.
    """
    url = f"{settings.MINERU_BASE_URL}/file_parse"

    # Build form data (based on reference implementation)
    form_data = {
        "backend": "pipeline",  # Use OCR pipeline (not VLM)
        "lang_list": "en",  # Can be made configurable later
        "formula_enable": str(settings.MINERU_ENABLE_FORMULA).lower(),
        "table_enable": str(settings.MINERU_ENABLE_TABLE).lower(),
        "return_md": "true",  # Get markdown text
        "return_content_list": "false",  # Don't need structured content
        "return_model_output": "false",
        "return_middle_json": "false",
        "return_images": "false",
        "response_format_zip": "false",  # Get JSON response, not ZIP
        "start_page_id": "0",
        "end_page_id": "99999"
    }

    try:
        async with httpx.AsyncClient(timeout=settings.MINERU_TIMEOUT) as client:
            # Open file and send to MinerU
            with open(image_path, "rb") as f:
                files = {"files": (image_path.name, f, "image/jpeg")}

                logger.debug(f"Sending {image_path.name} to MinerU at {url}")
                response = await client.post(
                    url,
                    data=form_data,
                    files=files
                )
                response.raise_for_status()

            # Parse JSON response
            json_resp = response.json()
            logger.debug(f"Received MinerU response: {len(json_resp)} bytes")

            # Extract markdown content from response
            # Response structure: {"results": {"<filename>": {"md_content": "..."}}}
            results = json_resp.get("results", {})
            if not results:
                logger.warning("MinerU returned empty results")
                return ""

            # Get first document result
            doc_key = list(results.keys())[0]
            doc_data = results[doc_key]
            markdown_text = doc_data.get("md_content", "")

            logger.info(f"Extracted {len(markdown_text)} chars from MinerU OCR")
            return markdown_text

    except httpx.HTTPError as e:
        logger.error(f"MinerU API request failed for {image_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in MinerU extraction for {image_path}: {e}")
        raise
