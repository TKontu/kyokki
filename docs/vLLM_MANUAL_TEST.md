# Manual vLLM Testing - Receipt Extraction Debug

This file contains everything needed to manually test receipt extraction with vLLM to debug the thinking loop issue.

## Problem Summary
- Simple receipts work fine (complete in <30s)
- Complex receipts timeout (>300s, never complete)
- Models tested: `qwen3-8B`, `Qwen3-4B-Instruct`
- Issue: Model appears stuck in thinking/reasoning loop before generating JSON

## Test 1: Simple Receipt (WORKS)

### Prompt:
```
Analyze this grocery store receipt and extract the products.

Receipt text:
```
PRISMA JYVÄSKYLÄ
S-KAUPAT OY

Maito 1 l                   1.49
Ruisleipä                   2.95
Juusto 400g                 4.50

YHTEENSÄ                    8.94
KORTTI                      8.94

Kiitos käynnistä!
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
```

### Expected Result:
Should complete in <30 seconds with valid JSON.

---

## Test 2: Real Receipt (FAILS - Thinking Loop)

### Prompt:
```
Analyze this grocery store receipt and extract the products.

Receipt text:
```
S-KAUPAT
Prisma ruoan verkkokauppa
AEROLANKAARI 3
01530 VANTAA
HOK-ELANTO LIIKETOIMINTA OY
1837957-3
TILAUSNRO: 1089366829
02.01.2026 11:40
----------------------------------------
KEVYTMAITOJUOMA LAKTON 1,28
OMENASOSE 1,99
MANGO KEITT/KENT/OSTEEN 1,50
0,386 KG 3,89 €/KG
COOP FETA JUUSTO PDO LAKTON 2,68
GRANAATTIOMENA 1,17
0,300 KG 3,89 €/KG
CHEDDAR PUNAINEN 3,43
TACO SAUCE MIETO LUOMU 1,99
RANSKANKERMA 18% VÄHÄLAKT 0,75
NACHO CHIPS 475G 2,99
AMERIKAN PEKONI ORIGINAL 2,49
KEISARINNA JUUSTO 6,72
BARISTA KAURAJUOMA 4,50
3 KPL 1,88 €/KPL
NORM. 5,64
ALENNUS -1,14
KOMPOSTOINTIPUSSI PAPERI 6,70
2 KPL 3,35 €/KPL
COOP ROSKAPUSSI 30L 25KPL MUSTA 6,15
3 KPL 2,05 €/KPL
RUISPALAT OHUT HERKKU 4,90
2 KPL 2,45 €/KPL
TIKKUPERUNAT 2,84
HAPANKAALI 4,39
OLIIVIÖLJY EXTRAVIRGIN 6,29
PORKKANA 1KG 5,45
5 KPL 1,09 €/KPL
OMENA GRANNY SMITH 3,80
1,590 KG 2,39 €/KG
PÄÄRYNÄ CONFERENCE I 1,01
0,484 KG 2,09 €/KG
PYYKKIETIKKA MARJAMETSÄ 11,38
2 KPL 5,69 €/KPL
NESTESAIPPUA OMENA 2,99
DIPPI SWEET CHILI 1,58
2 KPL 0,79 €/KPL
SIENILIINA 2,38
2 KPL 1,19 €/KPL
KEITTIÖSUIHKE SITRUS 3,15
YLEISPUHDISTUSSUIHKE 3,29
GLÖGI TUMMA SOKEROIMATON 1L 2,00
2 KPL 1,99 €/KPL
NORM. 3,98
ALENNUS -1,98
TURKKILAINEN JOGURTTI 10% 1,38
TUMMA RYPÄLE 500G 3,69
PUNASIPULI 0,52
0,330 KG 1,59 €/KG
SYDÄNSALAATTI 200G 1,29
TOMAATTIPYREE 0,59
NAMIVITA MONIVITAMIINI 16,95
KAURAJUOMA 5,64
3 KPL 1,88 €/KPL
LIME 2,21
0,740 KG 2,99 €/KG
KANAN FILEESUIKALE MTON 2,89
MOZZARELLA JUUSTORASTE 150G 1,28
PKARKEA VEHNÄJAUHO 1,28
KERMAVIILI 12% VÄHÄLAKT 0,98
2 KPL 0,49 €/KPL
PERSILJA 1,29
TOMAATTI SUOMI 4,59
1,180 KG 3,89 €/KG
ISOT KANANMUNAT VAPAA L15 3,77
OIVARIINI NORMAALISUOLAINEN 4,27
BANAANI 0,70
0,370 KG 1,89 €/KG
OMENA SUOMI 1,15
0,384 KG 2,99 €/KG
KIRSIKKATOMAATTI 250G 2,79
MONIVITAMIINI APPELSIINI 1,19
KURKKU 1,23
0,325 KG 3,79 €/KG
VERKKOK.PAKKAUSMATERIAALIMAKSU 2,55
TOIMITUSMAKSU 11,90 11,90
----------------------------------------
VÄLISUMMA 173,92
YHTEENSÄ 173,92
BONUSTA KERRYTTÄVÄT OSTOK 173,92
MAKSUTAPA Korttimaksu
Kortti: Mastercard Credit
************6568
Veloitus: 173,92
Autentisointi: FW88SHFFHDVXS9G3
Viite: 1089366829
Aika: 02.01.2026 11:41
ALV VEROTON VERO VEROLLINEN
25,5% 31,13 7,93 39,06
13,5% 118,80 16,06 134,86
YHT. 149,93 23,99 173,92
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
```

### Problem:
- Takes >300 seconds and never completes
- KV cache usage hits 90%
- Model appears to generate thousands of lines before/during JSON output

---

## Expected JSON Schema

```json
{
  "type": "object",
  "properties": {
    "store": {
      "type": "object",
      "properties": {
        "name": {"type": ["string", "null"]},
        "chain": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "language": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]}
      }
    },
    "products": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "name_en": {"type": ["string", "null"]},
          "quantity": {"type": "number", "minimum": 0, "default": 1.0},
          "weight_kg": {"type": ["number", "null"], "minimum": 0},
          "volume_l": {"type": ["number", "null"], "minimum": 0},
          "unit": {"type": "string", "default": "pcs"},
          "price": {"type": ["number", "null"], "minimum": 0}
        },
        "required": ["name"]
      }
    },
    "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1}
  },
  "required": ["products"]
}
```

---

## Manual Testing with curl

### Test Simple Receipt (should work):

```bash
curl -X POST http://192.168.0.247:9003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d '{
    "model": "Qwen3-4B-Instruct",
    "messages": [
      {
        "role": "user",
        "content": "Analyze this grocery store receipt and extract the products...[PASTE SIMPLE RECEIPT PROMPT]"
      }
    ],
    "temperature": 0.1,
    "max_tokens": 4096,
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "receipt_extraction",
        "schema": {...},
        "strict": true
      }
    }
  }'
```

### Test Real Receipt (reproduces thinking loop):

```bash
curl -X POST http://192.168.0.247:9003/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ollama" \
  -d @- <<'EOF'
{
  "model": "Qwen3-4B-Instruct",
  "messages": [
    {
      "role": "user",
      "content": "Analyze this grocery store receipt and extract the products...[PASTE REAL RECEIPT PROMPT]"
    }
  ],
  "temperature": 0.1,
  "max_tokens": 4096
}
EOF
```

**Watch for:**
- Response time >30 seconds
- vLLM logs showing KV cache filling
- Very long output before JSON starts

---

## Debugging vLLM Configuration

### Check vLLM Server Settings:

```bash
# Check if model has reasoning/thinking enabled
curl http://192.168.0.247:9003/v1/models

# Check vLLM server logs for configuration
# Look for: max_model_len, enable_prefix_caching, etc.
```

### Possible Fixes to Try:

1. **Disable reasoning mode** (if available in model config)
2. **Try non-reasoning model**: `Llama-3.1-8B-Instruct`, `Mistral-7B-Instruct`
3. **Add system message**:
   ```json
   {
     "role": "system",
     "content": "You are a receipt parser. Output ONLY valid JSON. Do not include any reasoning, thinking, or explanations. Just the JSON."
   }
   ```
4. **Reduce max_tokens** further: Try `2048`, `1024`
5. **Check vLLM launch params**: Ensure no `--enable-thinking` or similar flags

---

## Expected Behavior

**Simple Receipt:**
- Complete in <30s
- Output ~500-1000 tokens
- Valid JSON with 2-3 products

**Real Receipt:**
- Should complete in <60s
- Output ~2000-3000 tokens
- Valid JSON with 30-40 products

**Current Behavior (Bug):**
- Real receipt takes >300s
- Never completes
- Appears to generate 10,000+ tokens

---

## Contact

If you find a solution, please update `backend/app/services/llm_extractor.py` with:
- Working model name
- Required vLLM parameters
- Any system message needed
