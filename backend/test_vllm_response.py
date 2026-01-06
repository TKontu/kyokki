#!/usr/bin/env python3
"""Quick script to test vLLM response format."""
import asyncio
import httpx

async def test_vllm():
    """Call vLLM and print raw response."""
    prompt = """Analyze this grocery store receipt and extract the products.

Receipt text:
```
PRISMA JYVÄSKYLÄ
S-KAUPAT OY

Maito 1 l                   1.49
Ruisleipä                   2.95
Juusto 400g                 4.50

YHTEENSÄ                    8.94
```

Extract each product with:
- name: Product name
- quantity: Number of items
- unit: "pcs", "kg", "l", or "unit"
- price: Price in local currency

Output as valid JSON only."""

    async with httpx.AsyncClient(timeout=60.0) as client:
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

        print("=" * 80)
        print("RAW LLM RESPONSE:")
        print("=" * 80)
        print(content)
        print("=" * 80)
        print(f"\nResponse length: {len(content)} chars")
        print(f"Starts with: {repr(content[:100])}")
        print(f"Contains '{{': {'{' in content}")
        print(f"First {{ at position: {content.find('{')}")

if __name__ == "__main__":
    asyncio.run(test_vllm())
