"""LLM-based receipt extraction using vLLM with structured output.

Language-agnostic extraction that works with any receipt format.
vLLM server provides OpenAI-compatible API with JSON schema support.
"""
import httpx
from app.core.config import settings
from app.core.logging import get_logger
from app.parsers.base import ReceiptExtraction, ParsedProduct, StoreInfo

logger = get_logger(__name__)

# Language-agnostic extraction prompt from adaptive parser spec
EXTRACTION_PROMPT_TEMPLATE = """Analyze this grocery store receipt and extract the products.

Receipt text:
```
{receipt_text}
```

This receipt may be in any language. Extract each product with:
- name: Product name as written (preserve original language)
- name_en: English translation if not already English (optional)
- quantity: Number of items (default 1)
- weight_kg: Weight in kg if sold by weight (null otherwise)
- volume_l: Volume in liters if applicable (null otherwise)
- unit: "pcs", "kg", "l", or "unit"
- price: Price in local currency (optional)

Also identify:
- store_name: The store name from the header
- store_chain: Parent chain if identifiable
- country: Country code (ISO 3166-1 alpha-2, e.g., "FI", "US", "DE")
- language: Primary language of receipt (ISO 639-1, e.g., "fi", "en", "de")
- currency: Currency code (ISO 4217, e.g., "EUR", "USD")

Important:
- Preserve original product names (don't translate the name field)
- Recognize quantity words in any language (pcs, KPL, Stk, st, szt, шт, 個, pièces)
- Recognize weight/volume units (kg, g, l, ml, oz, lb)
- Handle various decimal separators (. or ,)
- Skip totals, tax lines, deposits, payment info regardless of language
- Only extract actual food/grocery products

Focus on extracting the products accurately. Be conservative - if you're not sure something is a product, skip it.
"""


async def extract_products_from_receipt(ocr_text: str) -> ReceiptExtraction:
    """Extract structured product data from receipt OCR text using LLM.

    Uses vLLM with OpenAI-compatible API and structured output (JSON schema).

    Args:
        ocr_text: Raw OCR text from receipt.

    Returns:
        ReceiptExtraction with products and store info.

    Raises:
        Exception: If LLM call fails or response is invalid.
    """
    logger.info("Extracting products from receipt using vLLM")

    # Build prompt
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(receipt_text=ocr_text[:4000])  # Limit to 4000 chars

    try:
        # Call vLLM with structured output (OpenAI-compatible API)
        logger.debug(f"Calling vLLM model: {settings.LLM_MODEL}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            headers = {
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.LLM_TEMPERATURE,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "receipt_extraction",
                        "schema": ReceiptExtraction.model_json_schema(),
                        "strict": True
                    }
                }
            }

            response = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Parse and validate response
            result = ReceiptExtraction.model_validate_json(content)

            logger.info(
                f"vLLM extraction complete: {len(result.products)} products, "
                f"store: {result.get_store_info().name or 'unknown'}"
            )

            return result

    except httpx.HTTPError as e:
        logger.error(f"vLLM API request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        raise


def build_prompt_for_store(ocr_text: str, store_hint: str | None = None) -> str:
    """Build extraction prompt with optional store hint.

    Args:
        ocr_text: OCR text from receipt.
        store_hint: Optional known store name to guide extraction.

    Returns:
        Formatted prompt string.
    """
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(receipt_text=ocr_text[:4000])

    if store_hint:
        prompt += f"\n\nNote: This receipt appears to be from {store_hint}. Use this to help identify the store chain and format."

    return prompt


async def extract_with_store_hint(ocr_text: str, store_hint: str) -> ReceiptExtraction:
    """Extract products with a known store hint.

    Useful when store detection found a match but confidence is low.

    Args:
        ocr_text: OCR text from receipt.
        store_hint: Known or suspected store name.

    Returns:
        ReceiptExtraction with products.
    """
    prompt = build_prompt_for_store(ocr_text, store_hint)

    logger.info(f"Extracting with store hint: {store_hint}")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            headers = {
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.LLM_TEMPERATURE,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "receipt_extraction",
                        "schema": ReceiptExtraction.model_json_schema(),
                        "strict": True
                    }
                }
            }

            response = await client.post(
                f"{settings.LLM_BASE_URL}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            result = ReceiptExtraction.model_validate_json(content)

            logger.info(f"Extraction with hint complete: {len(result.products)} products")

            return result

    except httpx.HTTPError as e:
        logger.error(f"vLLM API request failed: {e}")
        raise
    except Exception as e:
        logger.error(f"LLM extraction with hint failed: {e}")
        raise
