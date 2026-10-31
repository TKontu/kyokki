"""OCR service for receipt text extraction.

Routes between pdfplumber (digital PDFs) and MinerU (photo receipts). When MinerU cannot be
reached, ``OCRUnavailableError`` lets the pipeline read the image with a vision model instead.
"""

import asyncio
import mimetypes
from io import BytesIO
from pathlib import Path

import httpx
import pdfplumber
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# A photo Telegram compressed (it caps the long side at 1280) leaves a receipt ~290 px
# wide, and MinerU then invents words instead of reading them: the deployed Lidl photo
# came back as "Lid1 Suont Ky Esooo-Harakallto". Enlarging that same image 3x turned it
# back into readable product lines and prices. Beyond 3x there is no detail to recover.
MAX_UPSCALE_FACTOR = 3
# Below this the enlargement is not worth a re-encode: a 1 px difference must not
# quadruple MinerU's work the way the old ceil() did (999 px -> 1998 px).
MIN_UPSCALE_FACTOR = 1.25
# A capture whose long side is already this big was not compressed for transport (an iPad
# scan is downsized to 2000 px, a phone photo is larger), so it is left alone. It also
# keeps a long stitched screenshot (700 x 30000) from being enlarged to hundreds of MP.
UPSCALE_LONG_SIDE_BELOW = 1600
# Upper bound on the enlarged image; beyond this the resize costs more memory than the
# detail it could recover is worth (no compose service sets a memory limit).
MAX_UPSCALED_PIXELS = 40_000_000
UPSCALE_JPEG_QUALITY = 95


class OCRUnavailableError(Exception):
    """The OCR service could not be reached, timed out, or failed on its side (5xx)."""


def is_pdf(file_path: str | Path) -> bool:
    return Path(file_path).suffix.lower() == ".pdf"


def content_type_for(file_path: str | Path) -> str:
    """MIME type from the file name, e.g. image/png; octet-stream when unknown.

    The stored name's suffix comes from the validated upload content type
    (receipt_ingest.SUFFIX_FOR_CONTENT_TYPE), so this round-trips.
    """
    guessed, _ = mimetypes.guess_type(str(file_path))
    return guessed or "application/octet-stream"


async def extract_text_from_receipt(file_path: str) -> str:
    """Extract text from receipt image or PDF.

    Routes:
    - PDF files → pdfplumber, then MinerU when the PDF has no text layer
    - Image files → MinerU OCR service (for photo receipts)

    A scanned or photographed receipt saved as a PDF has no text layer, so
    pdfplumber returns "". That used to be handed straight to the model, which
    read nothing, and the receipt completed with zero lines (H07). MinerU's
    /file_parse accepts PDFs, so it is the same OCR call the image path makes.

    Raises:
        ValueError: If file type unsupported.
        OCRUnavailableError: If MinerU cannot be reached or fails on its side.
        httpx.HTTPError: For other MinerU request failures.
    """
    path = Path(file_path)

    if is_pdf(path):
        logger.info("Extracting text from PDF", extra={"file": path.name})
        text = await asyncio.to_thread(_extract_from_pdf, path)
        if text.strip():
            return text
        logger.info(
            "PDF has no text layer, sending it to MinerU", extra={"file": path.name}
        )
        return await _extract_from_image(path)
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


def prepare_image_upload(image_path: str | Path) -> tuple[str, bytes, str]:
    """What to send MinerU: ``(name, bytes, content type)``, enlarged when it is narrow.

    Telegram hands the bot a compressed photo (long side 1280), which leaves a receipt
    a few hundred pixels wide - too little for MinerU or the vision model to read. The
    enlargement is off for a capture whose long side is already large enough, and any
    decode failure (a test double, a format Pillow does not know, a decompression bomb,
    an out-of-memory resize) sends the original bytes untouched: OCR quality must never
    be able to fail a receipt.
    """
    image_path = Path(image_path)
    raw = image_path.read_bytes()
    content_type = content_type_for(image_path)
    minimum_width = settings.MINERU_UPSCALE_BELOW_WIDTH
    if minimum_width <= 0:
        return image_path.name, raw, content_type

    try:
        with Image.open(BytesIO(raw)) as stored:
            # EXIF orientation decides which side is the receipt's width; transposing
            # first also bakes the rotation into the pixels we send.
            image = ImageOps.exif_transpose(stored)
            width, height = image.size
            if (
                min(width, height) >= minimum_width
                or max(width, height) >= UPSCALE_LONG_SIDE_BELOW
            ):
                return image_path.name, raw, content_type
            factor = min(MAX_UPSCALE_FACTOR, minimum_width / min(width, height))
            if factor < MIN_UPSCALE_FACTOR:
                return image_path.name, raw, content_type
            enlarged_size = (round(width * factor), round(height * factor))
            if enlarged_size[0] * enlarged_size[1] > MAX_UPSCALED_PIXELS:
                logger.info(
                    "skipped enlarging a receipt image that is already large enough",
                    extra={"file": image_path.name, "size": list(image.size)},
                )
                return image_path.name, raw, content_type
            enlarged = image.convert("RGB").resize(
                enlarged_size, Image.Resampling.LANCZOS
            )
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        MemoryError,
    ):
        logger.debug(
            "could not decode the image for enlargement",
            extra={"file": image_path.name},
        )
        return image_path.name, raw, content_type

    buffer = BytesIO()
    enlarged.save(buffer, format="JPEG", quality=UPSCALE_JPEG_QUALITY)
    logger.info(
        "enlarged a small receipt image for OCR",
        extra={
            "file": image_path.name,
            "was": [width, height],
            "now": list(enlarged_size),
        },
    )
    # The bytes are JPEG now, so the part's name must say so: MinerU (and anything else
    # dispatching on the suffix) must not be handed a .png that is a JPEG.
    return image_path.with_suffix(".jpg").name, buffer.getvalue(), "image/jpeg"


async def prepared_image_upload(image_path: str | Path) -> tuple[str, bytes, str]:
    """`prepare_image_upload` off the event loop; the decode/resize/encode blocks."""
    return await asyncio.to_thread(prepare_image_upload, image_path)


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

    name, data, upload_content_type = await prepared_image_upload(image_path)

    try:
        async with httpx.AsyncClient(timeout=settings.MINERU_TIMEOUT) as client:
            files = {"files": (name, data, upload_content_type)}
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
