#!/usr/bin/env python3
"""Quick script to test vLLM response format with real receipt."""
import asyncio
import httpx
import pdfplumber

async def test_vllm():
    """Call vLLM with real receipt and check for truncation."""
    # Extract text from PDF
    with pdfplumber.open("samples/s_group_receipt.pdf") as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
        ocr_text = "\n".join(pages)

    print(f"OCR text length: {len(ocr_text)} chars")

    prompt = f"""Analyze this grocery store receipt and extract the products.

Receipt text:
```
{ocr_text[:4000]}
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

OUTPUT INSTRUCTIONS:
Return ONLY valid JSON with no explanations, no markdown formatting, no code blocks.
Start your response directly with the opening brace {{{{}}}}.
"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "model": "Qwen3-4B-Instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        response = await client.post(
            "http://192.168.0.247:9003/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": "Bearer ollama",
                "Content-Type": "application/json",
            }
        )

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        finish_reason = data["choices"][0].get("finish_reason", "unknown")
        usage = data.get("usage", {})

        print("=" * 80)
        print("RAW LLM RESPONSE (last 500 chars):")
        print("=" * 80)
        print(content[-500:])
        print("=" * 80)
        print(f"\nResponse length: {len(content)} chars")
        print(f"Finish reason: {finish_reason}")
        print(f"Token usage: {usage}")
        print(f"Starts with: {repr(content[:50])}")
        print(f"Ends with: {repr(content[-50:])}")
        print(f"\nIs valid JSON ending: {content.rstrip().endswith('}')} or {content.rstrip().endswith(']')}")

if __name__ == "__main__":
    asyncio.run(test_vllm())
