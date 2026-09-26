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

---

## MVP-R0 spike protocol (added 2026-09-13)

Time-box: 2 hours. Input: the "Test 2: Real Receipt" text above. Pass bar: one candidate
completes it in under 60 s with at least 80 % of product lines extracted. Record timings and
the working request here. Full rationale: `docs/PLAN_REVIEW_2026-09-13.md` section 1 (C1).

### Candidate A — text LLM after OCR (current design), in this order

1. Thinking off: add `"chat_template_kwargs": {"enable_thinking": false}` to the request
   (vLLM, Qwen3 hybrid models) or append `/no_think` to the prompt.
2. `max_tokens`: 4096. A 40-product receipt is roughly 2500 output tokens.
3. Trim the prompt to the fields the MVP reads: `name`, `quantity`, `unit`, `weight_kg`,
   `volume_l`. Drop `name_en`, `price`, `country`, `language`, `currency`, `confidence`.
4. Pre-filter OCR lines before the prompt with the skip patterns from `ARCHITECTURE.md`
   (`YHTEENSÄ`, `VÄLISUMMA`, `ALV`, `Kortti:`, `Viite:`, `TOIMITUSMAKSU`, `NORM.`, `ALENNUS`,
   `BONUSTA`, the VAT table, card and reference lines).
5. With thinking off, retry `response_format: {"type": "json_schema", ...}`.
6. If still over budget: split product lines into batches of ~15, one call each, merge.

### Candidate B — vision model straight from the image

Same endpoint with a vision-capable model (Qwen2.5-VL class), the receipt photo as an
`image_url` part, and the trimmed prompt. One step; no OCR language setting; sees layout
(indented `n KPL` lines, columns). Same thinking-off and `max_tokens` rules apply.

### Record per run

Run on 2026-09-14 against the llama-swap gateway `http://192.168.0.94:9292/v1`, using only models
pinned to the one available RTX 3090 (`GPU-a8c640ca-...`). Harness:
`docs/spikes/r0_extraction_spike.py` (ground truth parsed from the receipt above, fuzzy name match
≥ 80, quantity and weight checked per line). "Found" below uses that fuzzy match; the exact
name accuracy is listed separately after the table because it differs for vision. MinerU was not deployed, so Candidate A used the
receipt text above as its "OCR output". Candidate B used that text rendered as an image
(Consolas, 1.2° tilt, slight blur, scaled to a 2000 px long edge, 503×1999): **cleaner than a
phone photo**, so vision results are an upper bound until a real photo is tried.

Ground truth: 49 product lines (42 food, 7 household), 11 with an `n KPL` line, 10 sold by weight;
the two fees (`VERKKOK.PAKKAUSMATERIAALIMAKSU`, `TOIMITUSMAKSU`) are not products.

| Candidate | Model | Settings | Wall time | Products found / expected | Notes |
| --- | --- | --- | --- | --- | --- |
| A text | `muse-glimmer` | full keys, json_schema | 54.2 s | 44/49* | *all 49 present; 5 short names carried the price ("LIME 2,21") |
| B vision | `muse-glimmer` | full keys, json_schema | 60.4 s | 44/49* | same five names with price |
| A text | `muse-glimmer` | full keys, json_schema, prompt "without the price", reasoning `none` | 55.9 s | 49/49 | qty 11/11, kg 10/10; 3361 output tokens |
| A text | `muse-glimmer` | same, reasoning `minimal` | 51.9 s | 49/49 | qty 11/11, kg 10/10 |
| A text | `muse-glimmer` | same, **no** json_schema | 58.4 s | 49/49 | schema costs nothing measurable |
| A text | `muse-glimmer` | **compact keys**, json_schema, reasoning `minimal` | 44.1 / 41.3 / 42.6 s | 49/49 ×3 | qty 11/11, kg 10/10; ~2400 output tokens |
| B vision | `muse-glimmer` | compact keys, json_schema, reasoning `minimal` | 48.6 / 53.3 / 50.8 s | 49/49 ×3 | qty 11/11, kg 10/10; third run kept the price in every name |
| A text | `muse-glimmer` | **compact keys, json_schema, reasoning `low`** (documented value) | 39.9 / 42.8 / 40.4 s | 49/49 ×3 | qty 11/11, kg 10/10; exact names 49/49 ×3 |
| B vision | `muse-glimmer` | **compact keys, json_schema, reasoning `low`** | 46.5 / 46.9 / 51.8 s | 49/49 ×3 | qty 11/11, kg 10/10; exact names 42, 41, 41; no prices in names |

`none` and `minimal` are **not** supported values (see findings); those rows are kept as
measured but the `low` rows are the reference configuration.
| A text | `gemma-26b` | compact keys, json_schema | 13.0 s | 49/49 | qty 11/11, kg 10/10; cold load 247 s |
| A text | `gemma-26b` | full keys, json_schema | 18.1 s | 49/49 | one name carried the price |
| B vision | `gemma-26b` | compact keys, json_schema | 12.9 s | 48/49 | qty 8/11, kg 9/10; vLLM gave the image ~450 tokens |
| A text | `qwen3.5-9b` | compact keys, json_schema | 26.4 s | 48/49 | qty 11/11, kg 10/10; cold load 220 s |
| B vision | `qwen3.5-9b` | compact keys, json_schema | 22.5 s | 49/49 | qty 8/11, **kg 2/10** |

Exact product names (after stripping a trailing price), per run:

| Model | Text | Vision |
| --- | --- | --- |
| `muse-glimmer` | 49/49 on all 9 runs | 42, 41, 41, 41, 42, 41, 41 /49 (≈ 8 misread names per receipt, e.g. `KEVYMAITOJUOMA`, `GRANAATT IOMENA`, `KEITTIÖSUHKE`) |
| `gemma-26b` | 49/49 | 26/49 |
| `qwen3.5-9b` | 47/49 | 48/49 (but weights 2/10) |

Findings:
- **`muse-glimmer` always reasons.** Per Meta's prompting guide
  (https://dev.meta.ai/docs/muse-glimmer/prompting), reasoning is built into the format (a
  private `assistant to=self` turn) and `reasoning_strength` accepts only `xhigh`, `high`,
  `medium` or `low` (template default `high`; this gateway's server default is `low`). There
  is no off switch and `enable_thinking` is ignored. `low` is the lowest supported setting;
  the `none`/`minimal` runs only rendered unsupported text into the template and behaved like
  `low`. Time scales with output tokens (~58 tok/s), so the lever is **output size**.
- **Stream long generations.** The guide recommends streaming for reasoning workloads so
  multi-thousand-token traces do not hit request timeouts. The spike used non-streaming
  calls under 60 s; R1 should stream (or at least set a generous client timeout).
- **Compact keys** (`{"p": [{"n", "q", "w"}]}`) cut ~25 % of output tokens and bring
  `muse-glimmer` under the bar with margin. The backend maps them to `ExtractedItem`.
- **"without the price"** in the name rule is needed, and still not sufficient for vision (one
  run in three kept every price). Strip a trailing `\s+\d+,\d{2}` in the backend regardless.
- **Vision reads counts and weights reliably but misspells ~1 in 6 names** even on a clean
  rendered image. Near-miss names still fuzzy-match existing products, and the review screen
  (R7) lets the user fix them, but new products would be created with misspelt names.
- `response_format: json_schema` works on both llama.cpp and vLLM here (no thinking loop, unlike
  the 2025 Qwen3 vLLM setup at the top of this file) and always produced valid JSON.
- The unit enum is unnecessary: quantity and weight are what the receipt states, and DEC-1
  conversion happens in the backend.
- Smaller models are fast on text but much worse at reading quantities and weights from the image.
- `muse-glimmer` is the always-loaded model on this gateway (a hot agent and an idle poller keep
  it up), so it has no cold-load cost. Any other model evicts it and costs 3–4 minutes cold.

### Working request (Candidate A, `muse-glimmer`)

```bash
curl -s http://192.168.0.94:9292/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "muse-glimmer",
  "max_tokens": 4096,
  "temperature": 0.2,
  "chat_template_kwargs": {"reasoning_strength": "low"},
  "response_format": {"type": "json_schema", "json_schema": {"name": "receipt", "strict": true,
    "schema": {"type": "object", "required": ["p"], "properties": {"p": {"type": "array",
      "items": {"type": "object", "required": ["n", "q", "w"], "properties": {
        "n": {"type": "string"}, "q": {"type": "number"}, "w": {"type": ["number", "null"]}}}}}}}},
  "messages": [{"role": "user", "content": "<COMPACT_INSTRUCTIONS>\n\nReceipt:\n<pre-filtered receipt text>"}]
}'
```

`COMPACT_INSTRUCTIONS` and the pre-filter regex are in the harness. Candidate B sends the same
instructions as a `text` part plus an `image_url` part (`data:image/png;base64,...`).

### Outcome

- **R0 passes.** `muse-glimmer` (`reasoning_strength: low`) completes the 60-line receipt in
  40–43 s from text and 47–52 s from an image, with 49/49 products
  and every quantity and weight correct, on both candidates; `gemma-26b` text does it in 13 s.
- **Model:** `muse-glimmer` for both paths. It is always loaded, gets every quantity and weight
  right from text and image, and is the only single-GPU model whose image reading holds up.
- **Primary path is not decided yet.** From perfect text, Candidate A is exact (49/49 names);
  from a clean image, Candidate B misspells ~8 names. But Candidate A's real input is MinerU OCR
  of a phone photo, which has not been measured (MinerU is offline until 2026-09-15). R4 decides
  with real photos: MinerU → text vs. image → vision, comparing exact names, counts and time.
  Until then R1 wires both: text for digital PDFs (pdfplumber) and whenever OCR text exists,
  vision for photos when MinerU is unreachable. The heuristic parser (R3b) stays last resort.
- DEC-4 (fallback if R0 failed) is not needed.
- For R1/R4: `config.py`, `.env.example` and `stack.env.example` still point at the retired
  endpoint `192.168.0.247:9003` with `LLM_MODEL=qwen3-8B`; `llm_extractor.py` still sends
  `max_tokens: 16384`, no schema, and the full-key prompt. The request above replaces that.
  Receipt processing must allow ~60 s per call (R3 runs it in the background).

## MVP-R2 generic product names (2026-09-14)

`muse-glimmer` on the llama-swap gateway, `reasoning_strength: low`, the compact contract with
the new `g` field. Harness: the R0 receipt text and renderer (`docs/spikes/r0_extraction_spike.py`).

**Text path, direct call:** 63.8 s, 49/49 lines, finish `stop`, **3758 completion tokens** of the
old 4096 `max_tokens` (1467 prompt). The default is now 8192. Generic names were brand- and
size-free: KEVYTMAITOJUOMA LAKTON → Milk, AMERIKAN PEKONI ORIGINAL → Bacon, KANAN FILEESUIKALE
MTON → Chicken fillet, ISOT KANANMUNAT VAPAA L15 → Eggs, PORKKANA 1KG → Carrot. Household lines
got a name and no category.

**Through the API (vision, rendered image), empty catalog, throwaway DB:**

| Step | Result |
| --- | --- |
| Receipt 1 process | 72.2 s, 49 lines, every line with a generic name, 0 matched (empty catalog) |
| Confirm receipt 1 | 41 food lines sent by `index` (8 without category skipped): 41 items, 38 products (Apple, Oat drink, Tomato reused within the confirm), 41 verified `s-group` aliases |
| Locations | 26 main_fridge, 14 pantry, 1 freezer (Potato sticks), all from the category |
| Confirm again | 409 "Receipt already confirmed" |
| Receipt 2 (K-Citymarket, other brands: ARLA, SNELLMAN, VALIO, PIRKKA, HK, RAINBOW, ELOVENA) | 28.0 s, **11/12 matched**, all `exact` on the generic name; the unmatched line (ATRIA NAUDAN JAUHELIHA → Ground beef) was not on receipt 1 |

Vision misreads carried into generic names: SIENILIINA (cleaning cloth) → Mushroom in
`produce`, TUMMA RYPÄLE (grapes) → Raisins; the text path named both correctly. KIRSIKKATOMAATTI
became "Tomato" on the image path. The review screen (R7) is where such lines get corrected.

## Homelab endpoints and model choice (2026-09-16)

The gateway now serves per-GPU copies of each model (`c0.*`, `c2.*`, plus unprefixed names that
pick a card themselves) and MinerU is back. **`c0` is reserved for the operator's Hermes agent**,
so Kyokki must name a `c2.*` model. 104 model entries; the c2 family is muse-glimmer, gemma-26b,
gemma-e4b, qwen3.5-4b, qwen3.5-9b, qwen3.8-27b, qwythos-v2, fablevibes and ternary.

| Endpoint | Address | Check |
| --- | --- | --- |
| Inference (OpenAI-compatible) | `192.168.0.94:9292/v1` | `c2.muse-glimmer` loaded on GPU `094f1ca3`, with vision (mmproj) |
| MinerU OCR | `192.168.0.94:8008` (container 8000) | `/health` 200, `/file_parse` as our client expects, GPU `689f1c3c` |

MinerU read the rendered receipt image in 20.6 s and returned 31 lines with product names intact,
so image receipts take the text path again instead of falling back to vision.

### Model comparison on the real contract (text path, generic names, same 60-line receipt)

| Model | Warm | Cold load | Lines | Quantities | Weights | Categorised | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `c2.muse-glimmer` | 56-66 s | ~10 s | 49/49 | 49/49 | 49/49 | 40/49 | singular names, best Finnish -> English |
| `c2.gemma-26b` | 15.9 s | ~299 s | 49/49 | 49/49 | 49/49 | 41/49 | fastest warm, but a five-minute cold load |
| `c2.qwen3.8-27b` | 205 s (100 s with `enable_thinking: false`) | ~208 s | 49/49 | 49/49 | 49/49 | 43/49 | plural names; several Finnish mistranslations |

All three read every line, quantity and weight, so **generic-name quality decided it**. The two
models disagreed on 28 of 49 names. Qwen turned PYYKKIETIKKA (laundry vinegar) into "Game sauce",
OIVARIINI (butter spread) into "Olives", TUMMA RYPÄLE into "Dark chocolate" and KERMAVIILI into
"Curd"; it also pluralises ("Apples", "Carrots"), which would split one product into two over
time because MVP-R2 reuses products by name. **`c2.muse-glimmer` stays the default.**

### Prompt tightening (same run set)

Two rules were added because every bad name came from the same two causes:
- *"Always write g in the singular"* with examples. Result: no plurals left except "Chips".
- *"Household and cleaning products get an everyday English name too … Their c is usually null;
  food keeps its category as below."* Result: SIENILIINA -> Cleaning cloth (was "Mushroom
  cloth"), PYYKKIETIKKA -> Laundry vinegar, NESTESAIPPUA -> Liquid soap, ROSKAPUSSI -> Trash bag.

The household rule **must** reassert that food keeps its category. A first version without that
sentence made the model return `c = null` for all 49 lines in three runs out of three. With the
sentence, categorised is back to 40/49.

Known miss: TUMMA RYPÄLE 500G (dark grapes) is still named "Raisin". Categorisation also varies
run to run: one pipeline run returned 0 categories and the repeat returned 40. The review screen
(R7) is where such lines get corrected.

### End-to-end through the deployed pipeline
Receipt photo -> MinerU -> `c2.muse-glimmer` -> matching, on a throwaway DB with the worker
running: `completed` in 70-73 s, method `text`, 49 items, 49 generic names, store `s-group`,
date 2026-01-02.


## MVP-R4 real-receipt validation (open, 2026-09-16)

**Acceptance:** 5/5 real receipts reach `completed` in under 120 s each, with at least 80 % of
their line items extracted. Five receipts still have to go through the deployed stack.

### Reading the numbers
Since `feat/mvp-p1-r6-r8-app-shell`, every read logs one line per receipt, and `JSONFormatter`
now publishes the extras it used to drop. On the homelab:

```
docker logs kyokki-worker 2>&1 | grep '"ocr_seconds"'
```

Each line carries `receipt_id`, `method` (`text` / `vision` / `heuristic`), `ocr_seconds`,
`llm_seconds`, `total_seconds`, `items_extracted` and `items_matched`. A failure logs the same
timings plus `error`. `items_extracted` against the printed line count gives the extraction rate;
no counting by hand.

### Runs

| # | Store | Method | OCR s | Model s | Total s | Extracted | Of printed | Matched | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | — | — | — | — | — | — | — | — | waiting for a real receipt |

Local dry run on the same pipeline (throwaway DB, the S-kaupat fixture rendered to PDF), to show
the shape of the record rather than to count towards the five:

| # | Store | Method | OCR s | Model s | Total s | Extracted | Matched | Result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | s-group | text | 0.1 | 60.2 | 60.4 | 49 | 0 | completed, confirmed to 40 items |

OCR is nothing on a digital PDF (pdfplumber, no MinerU call); the model is the whole cost. OCR
language only becomes a measured variable once a photographed receipt goes through MinerU.


## Does the prompt still need the catalog? (H17, 2026-09-18)

The extraction prompt lists up to 300 catalog names so the model reuses them and generic names
stay consistent between receipts. Since H11 a name is a key and confirm learns the generic name
as a synonym, so the spec expected the block to be droppable
(`docs/PRODUCT_RESOLUTION_SPEC.md` §3.6). Measured on the 49-line S-kaupat fixture against
`c2.muse-glimmer`, with a 20-name warm catalog, twice:

| run | prompt chars | model s | lines read | with generic name | with category |
| --- | --- | --- | --- | --- | --- |
| with catalog | 2983 | 71.9 | 49 | 49 | **40** |
| without catalog | 2657 | 64.7 | 49 | 49 | **31** |
| with catalog (2nd) | 2983 | 74.5 | 49 | 49 | **40** |
| without catalog (2nd) | 2657 | 77.0 | 49 | 49 | **30** |

**The block stays on.** Line and generic-name quality hold either way - 49 of 49 both times -
but the categories the model fills in drop from 40 to 30-31, and the 40 figure is the baseline
`HANDOFF.md` tells the next session to check a real receipt against. Extraction is not reliably
faster either: 64.7 s then 77.0 s without, against 71.9 s and 74.5 s with. `EXTRACTION_OFFERS_CATALOG`
exists to turn it off, per the spec's "keep it behind a setting for one release if it regresses".

Worth revisiting, and worth knowing: **without the catalog the model chooses more specific
names.** It produced `Cherry tomato`, `Feta cheese`, `Mozzarella`, `Olive oil` and `Nacho chips`
where the catalog-anchored run gave `Tomato`-shaped generics like `Cabbage`, `Chips`, `Dip`,
`Oil` and `Sauce`. For a catalog that is meant to be generic-but-not-wrong that is arguably the
better answer - `docs/PRODUCT_RESOLUTION_SPEC.md` §1 is explicit that Cherry tomato is *not*
Tomato - so this is worth measuring again once real synonyms have accumulated, rather than
treating the category count as the last word.


## The catalog block was silencing the estimates (Q7, 2026-09-19)

The first real receipt came back with `sl: null` for every meat line, so mince, ham, sausage and
chicken fillet all fell back to the `meat` category's blanket 5 days - too long for mince and far
too short for salami. The plan assumed the prompt lacked meat examples. **It did not.** Measured
on the 49-line fixture with an empty catalog, the model estimates meat perfectly well:
`AMERIKAN PEKONI -> 21`, `KANAN FILEESUIKALE -> 2`, and 39 of 49 lines get a shelf life at all
(the 10 without are household and cleaning products, which correctly have none).

The cause was the known-products block, which ended *"and set pw, sl and os to null for it - the
system already knows those"*. It was meant to save re-deriving what the catalog holds. The model
applied it to the **whole receipt** rather than to the listed products. Two runs each, same
fixture, with a 14-name catalog offered:

| prompt | shelf lives | opened shelf lives | piece weights | model s |
| --- | --- | --- | --- | --- |
| with the clause | **4**, then **12** of 49 | 1, then 7 | 6, 6 | 88.8, 87.0 |
| clause removed | **37**, then **39** of 49 | 17, 17 | 6, 7 | **69.8, 70.6** |
| *(no catalog at all, for reference)* | 39 | — | 7 | 64.5 |

Note the instability in the old rows - 4 then 12 - which is the model guessing differently each
time about how widely the instruction applied. That alone is a reason to remove it.

**Removing the clause is better on both axes and needs no trade:** estimates come back, and
extraction is about **20 % faster** (≈88 s to ≈70 s), because the model no longer reasons about
which products to skip. Estimating for a product the catalog already knows costs a few tokens and
is discarded by `_fill_gaps` anyway; *not* estimating cost the catalog its accuracy.

This also revises the H17 entry above: the catalog block costs roughly 6 s (64.5 s cold against
≈70 s warm) rather than being free, but it no longer destroys the per-product estimates that Q2
and Q6 exist to produce.

**No meat examples were added to the prompt.** The fixture shows they are not needed, and an
unmeasured change to a measured artefact is how this problem started.

## The model cannot be asked for a pack weight (Q8, 2026-09-19)

Q8 wants the 400 g in a pack of mince, which no Finnish receipt prints. The plan's first source
was a `pk` field in the extraction contract - *what one pack of this weighs in grams* - measured
against a ~90 s cost gate before committing. It was measured, and **it failed on quality, not on
time.** Two runs each, 49-line fixture, `c2.muse-glimmer`, 14-name catalog, Q7's prompt:

| contract | shelf lives | opened shelf lives | pack weights | model s |
| --- | --- | --- | --- | --- |
| `n g q w c pw sl os` | 39, 40 of 49 | 19, 20 | — | 69.4, 70.7 |
| `+ pk` | **26**, then **4** of 49 | 13, then 2 | **1**, 1 | 70.9, 76.3 |

`pk` was answered on **one line of forty-nine**, and the fourth estimate per line collapsed the
three that already worked - the same 4-of-49 instability Q7 had just fixed, and the same failure
mode twice: **muse-glimmer's per-line estimates are fragile to prompt complexity.** Time stayed
inside the gate; the answers did not survive.

So `pk` was reverted, and pack weight has three sources, none of them the model:

1. **A size printed in the product name** - `SIPULI 500G`, `KIRSIKKATOMAATTI 250G`. A
   deterministic parse (`grams_from_name`) of `G`/`KG` only: `COOP ROSKAPUSSI 30L 25KPL` and
   `GLOGI ... 1L` are not weights. 8 of the 49 fixture lines carry one, for no model cost at all.
2. **The catalog**, once a product knows its pack weight.
3. **The cook**, in the product editor's *One pack* field - one correction per product, ever.

That is the fallback the plan wrote down in advance, and it is the whole feature with a cheaper
source: mince costs one correction and is then right for every later receipt from any shop.

**The standing rule this round confirms:** measure a contract change against this fixture before
keeping it, and count the *other* estimates too, not just the new field's. Both times a field was
added on reasoning alone, the damage showed up somewhere else in the response.

## Asking the model about the catalog instead of the receipt (Q11, 2026-09-19)

Q7 fixed why the model had stopped estimating shelf lives. It repaired nothing already
stored: on the homelab **46 of 50 products carried their category's blanket figure**, all six
meat products read 5 days, and `Rye crispbread` sat at 5 while the model's own 720 lay unused in
a receipt still in the database. The receipts that created those products are `confirmed`, which
is terminal, and for 45 of the 46 no estimate was ever made at all.

So Q11 asks directly, about **names** rather than receipt lines, through a separate prompt in
`services/catalog_estimates.py`. Measured on the real 46 candidate names pulled from the homelab:

| run | answered | seconds |
| --- | --- | --- |
| 1 | **46 of 46** | 51.8 |
| 2 | **46 of 46** | 55.2 |
| 3 | **46 of 46** | 54.5 |
| 4 | **46 of 46** | 56.6 |

Full coverage every time, in under a minute for the whole catalog — cheaper than one receipt
read, because there is no OCR and no per-line work. And the answers are the ones the complaint
was about:

```
Ground beef      5 -> 2     Rye crispbread   5 -> 720   (the June receipt's own number)
Chicken fillet   5 -> 3     Milk             7 -> 7
Chicken          5 -> 3     Yogurt           7 -> 21
Ham              5 -> 10    Sour cream       7 -> 30
Sausage          5 -> 14    Olive oil      365 -> 540
Bacon            5 -> 21    Rice           365 -> 720
```

Six meat products that were one number are now six different numbers, and mince — the only
safety issue in the whole friction log — is 2 days.

### The honest part: the answers move between runs

Comparing two runs product by product, **31 of 46 are identical and 15 differ**:

```
Bacon      14 / 21      Cheese     30 / 45      Dip       180 / 30
Feta       30 / 60      Egg        35 / 28      Kiwi        7 / 14
Mozzarella 21 / 30      Ginger     60 / 30      Cucumber   14 / 10
Olive oil 365 / 720     Orange juice 180 / 21   Chips     365 / 180
```

All inside a sensible band — none is absurd — but "ask again and get a different number" is
real, and the design answers it in two places rather than pretending otherwise:

1. **A dry run is the default.** The proposed numbers are shown before anything is written, so
   the coin toss happens in front of the cook rather than behind them.
2. **Applying sets `shelf_life_source = 'model'`**, and a refresh only ever considers `category`
   rows. So the variation is a one-time choice, not weekly churn — a second refresh straight
   after the first considers **zero** products.

The safety-critical answers are also the stable ones: Ground beef 2/2, Chicken fillet 3/3,
Ham 10/10, Milk 7/7, Rye crispbread 720/720.

A band per category (`PLAUSIBLE_DAYS`) rejects anything outside what its category could possibly
mean — 400 days of mince is a confident wrong answer, and this writes to 46 rows at once. A
rejected answer is not a failure: the product keeps the placeholder it already had.

### The control, which is the point of a separate prompt

Twice this month a change to `_INSTRUCTIONS` destroyed estimates it was not aimed at (Q7, Q8),
both silently. This prompt lives in its own module and cannot reach the receipt path. Re-running
the **unchanged 49-line fixture** on the Q11 branch, where `llm_extractor.py` and `parsers/` are
byte-identical to `main`:

| run | lines | shelf lives | meat/fish with one | seconds |
| --- | --- | --- | --- | --- |
| 1 | 49 | **18** of 49 | 0 of 2 | 67.5 |
| 2 | 49 | **39** of 49 | 2 of 2 | 68.9 |
| 3 | 49 | **39** of 49 | 2 of 2 | 67.1 |

Runs 2 and 3 match Q7's recorded baseline exactly. **Run 1 is an outlier and it is worth
recording rather than discarding:** with the prompt, the contract and the fixture all identical,
the same call produced 18 shelf lives instead of 39. Nothing in the branch can explain it — the
extraction files are untouched — so this is the model, not the code.

That is the third time this month the two-run rule has earned itself, and it sharpens the rule:
**a single run cannot distinguish a regression from muse-glimmer having an off day, in either
direction.** A one-run measurement showing 18 would have looked exactly like a prompt regression.

## Finnish glossary (H54) and the live selection run (H53), 2026-09-25

Q14 reported three Finnish words read wrongly: TUMMA RYPÄLE became *Raisin*, TIKKUPERUNAT
*Potato*, and a MONIVITAMIINI juice *Multivitamin*. H54 adds a glossary to `_INSTRUCTIONS`.
Measured on the production prompt path for the first time: `scripts/measure_extraction.py` calls
the real `extract_from_text` with the 13 seeded categories and an **empty catalog**, no database.
`c2.muse-glimmer` at `http://192.168.0.94:9292/v1`, reasoning `low`, temperature 0.1:

```
cd backend && LLM_BASE_URL=http://192.168.0.94:9292/v1 LLM_MODEL=c2.muse-glimmer \
  .venv/bin/python -m scripts.measure_extraction --runs 2 \
  --fixture tests/fixtures/receipts/s_kaupat_order.txt \
  --fixture tests/fixtures/receipts/glossary_terms.txt
```

`glossary_terms.txt` is a synthetic 9-line receipt for the words the S-kaupat fixture lacks
(RIISIPIIRAKKA, KARJALANPIIRAKKA, VALMISRUOKA, ATERIA, TÄYSMEHU, APPELSIINIMEHU) plus RUSINA, a
real raisin, as the control. It has no header comment: the skip rules would pass one to the model.

### The 49-line fixture, before and after

| prompt | chars | model s | lines | generic | category | sl | os | pw |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| before (main) | 4431 | 74.6 | 49 | 49 | 40 | 39 | 18 | 7 |
| before (main), 2nd | 4431 | 62.2 | 49 | 49 | 40 | 39 | 19 | 7 |
| attempt 1: block after the household rule | 4810 | 64.3 | 49 | 49 | 41 | 40 | 18 | 6 |
| attempt 1, 2nd | 4810 | 71.1 | 49 | 49 | 41 | **6** | **3** | 7 |
| attempt 2: one arrow-style rule after the g examples | 4790 | 67.0 | 49 | 49 | 41 | 40 | 18 | 6 |
| attempt 2, 2nd | 4790 | 65.7 | 49 | 49 | 41 | **6** | **4** | 5 |
| **attempt 3 (kept)**: rule last + "for every food line" | 4839 | 73.0 | 49 | 49 | 41 | 41 | 23 | 10 |
| attempt 3, 2nd | 4839 | 71.4 | 49 | 49 | 41 | 41 | 24 | 9 |
| attempt 3, 3rd | 4839 | 66.8 | 49 | 49 | 41 | 41 | 25 | 10 |
| attempt 3, 4th | 4839 | 65.0 | 49 | 49 | 41 | 41 | 20 | 7 |

(`category` counts food categories; the household lines come back with a null `c`, before and
after alike.) Three more runs of attempt 2's wording, to see the failure: 40, 40, then **10**
shelf lives. The collapsed run answered `sl` only where the prompt carries the number itself -
milk 10, hard cheese 30, carrot 21, banana 7, apple 14, flour 720 - and null for bacon, chicken,
grapes, eggs and the rest: the Q7 failure again, with a list of term -> answer lines teaching the
model that the examples *are* the table. Attempt 3 moves the glossary to the end of the rules and
tells the sl rule that its examples are not the list (*"Estimate it for every food line, not only
these"*); 4 runs of 4 kept 41 shelf lives. The Q11 control above shows the unchanged prompt can
also have an off run (18), so 3 collapses in 7 is a lean, not a proof - but 4 clean of 4 after the
fix, with sl and os both **above** the baseline, is what the gate asks for.

### The watch list

| printed | before (both runs) | after, attempt 3 (all runs) |
| --- | --- | --- |
| TIKKUPERUNAT | Potato (produce) | **French fries (frozen)** |
| TUMMA RYPÄLE 500G | Raisin (pantry) | **Grape (fruits)** |
| NAMIVITA MONIVITAMIINI | Multivitamin (null) | Vitamin supplement (null) - not a juice |
| MONIVITAMIINI APPELSIINI | Multivitamin (null) | **Multivitamin juice (beverages)** |
| RIISIPIIRAKKA 10KPL | Rice pie (ready_meals) | **Karelian pasty (bread)** |
| KARJALANPIIRAKKA | Pie (bread) | **Karelian pasty (bread)** |
| VALMISRUOKA LIHAPULLAT | Meatballs (ready_meals) | Meatballs / Meatball (ready_meals) |
| ATERIA KANAKASTIKE | Chicken sauce / stew (ready_meals) | Chicken stew / meal (ready_meals) |
| TÄYSMEHU OMENA 1L | Apple juice (beverages) | Apple juice (beverages) |
| APPELSIINIMEHU | Orange juice (beverages) | Orange juice (beverages) |
| RUSINA 250G | Raisins / Raisin (pantry) | Raisin (pantry) - the control holds |

The glossary fixture itself: 9 of 9 lines, generic names, categories and shelf lives in every run,
before and after (prompt 2973 -> 3381 chars, 23-25 s):

| prompt | chars | model s | lines | generic | category | sl | os | pw |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| before (main) | 2973 | 23.8 | 9 | 9 | 9 | 9 | 9 | 0 |
| before (main), 2nd | 2973 | 24.1 | 9 | 9 | 9 | 9 | 9 | 0 |
| attempt 1 | 3352 | 24.0 | 9 | 9 | 9 | 9 | 9 | 2 |
| attempt 1, 2nd | 3352 | 22.9 | 9 | 9 | 9 | 9 | 8 | 0 |
| attempt 2 | 3332 | 25.7 | 9 | 9 | 9 | 9 | 8 | 0 |
| attempt 2, 2nd | 3332 | 23.7 | 9 | 9 | 9 | 9 | 8 | 0 |
| **attempt 3 (kept)** | 3381 | 24.9 | 9 | 9 | 9 | 9 | 9 | 2 |
| attempt 3, 2nd | 3381 | 24.4 | 9 | 9 | 9 | 9 | 9 | 0 |
 Attempt 1 wrote `MEHU, TÄYSMEHU = juice`
and the model then flattened TÄYSMEHU OMENA to plain *Juice* in one run; the kept wording uses
`TÄYSMEHU OMENA -> "Apple juice"` so the fruit survives. The prompt grows by 408 characters
on every receipt (359 for the glossary, the rest for the sl clause):

```
- Finnish words often misread: TUMMA RYPÄLE -> "Grape" (RUSINA is "Raisin"); TIKKUPERUNAT
  -> "French fries"; TÄYSMEHU OMENA -> "Apple juice" (MEHU is juice); RIISIPIIRAKKA ->
  "Karelian pasty"; MONIVITAMIINI APPELSIINI -> "Multivitamin juice", but MONIVITAMIINI
  with no flavour is a vitamin supplement, household; VALMISRUOKA, ATERIA -> c = ready_meals.
```

**Merge gate: holds** on every attempt-3 run. TIKKUPERUNAT, TUMMA RYPÄLE, both MONIVITAMIINI
lines, riisipiirakka, the ready meals and RUSINA read as specified; on the 49-line fixture lines
(49), generic names (49) and categories (41 against 40) are not below baseline, and sl (41) and
os (20-25) clear the gate's floor of 2 below the baseline minimum (37 and 16); both are in fact
above the baseline (39, 18-19). The supplement still gets a null `c`
rather than `household`, as the household products do - not a juice, which is what the gate asks.

### With the catalog on: the production prompt (2026-09-26)

The runs above offered an **empty catalog**, but production runs `EXTRACTION_OFFERS_CATALOG=True`
(H17), and Q7 is the precedent for the catalog block silencing `sl`. So the gate was run again
on the production prompt path: `--catalog 20` offers a fixed 20-name warm catalog (in the script:
Milk, Lactose-free milk, Oat drink, Feta cheese, Cheddar, Bacon, Chicken fillet strips, Ground
beef, Eggs, Butter, Tomato, Cucumber, Carrot, Onion, Banana, Apple, Potato, Rye bread, Orange
juice, Chips - the Q7/H17 names were not recorded, so this is a new list, with Potato in it on
purpose). Main's prompt was measured from a scratch checkout of `b2c10ad` with the same script
copied in. Same model, gateway and settings:

```
cd backend && LLM_BASE_URL=http://192.168.0.94:9292/v1 LLM_MODEL=c2.muse-glimmer \
  .venv/bin/python -m scripts.measure_extraction --catalog 20 --runs 2 \
  --fixture tests/fixtures/receipts/s_kaupat_order.txt \
  --fixture tests/fixtures/receipts/glossary_terms.txt
```

| fixture | prompt | chars | model s | lines | generic | category | sl | os | pw |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 49-line | before (main) | 4717 | 95.8 | 49 | 49 | 40 | 40 | 22 | 6 |
| 49-line | before (main), 2nd | 4717 | 71.5 | 49 | 49 | 40 | 39 | 18 | 7 |
| 49-line | **after (glossary)** | 5125 | 68.6 | 49 | 49 | 41 | 41 | 19 | 6 |
| 49-line | after (glossary), 2nd | 5125 | 68.6 | 49 | 49 | 41 | 41 | 20 | 9 |
| glossary | before (main) | 3259 | 17.6 | 9 | 9 | 9 | **1** | **1** | 0 |
| glossary | before (main), 2nd | 3259 | 17.3 | 9 | 9 | 9 | **3** | **3** | 0 |
| glossary | after (glossary) | 3667 | 23.4 | 9 | 9 | 9 | 9 | 9 | 0 |
| glossary | after (glossary), 2nd | 3667 | 24.7 | 9 | 9 | 9 | 9 | 8 | 0 |

| printed | before, catalog on (run 1 / run 2) | after, catalog on (both runs) |
| --- | --- | --- |
| TIKKUPERUNAT | Potato (produce) / Potato (frozen) | **French fries (frozen)** |
| TUMMA RYPÄLE 500G | Raisin (pantry) / Grape (fruits) | **Grape (fruits)** |
| NAMIVITA MONIVITAMIINI | Multivitamin (null) | Vitamin supplement (null) - not a juice |
| MONIVITAMIINI APPELSIINI | Multivitamin / Vitamin (null) | **Multivitamin juice (beverages)** |
| RIISIPIIRAKKA 10KPL | Rice pie (ready_meals) | **Karelian pasty (bread)** |
| KARJALANPIIRAKKA | Pie / Karelian pie (ready_meals) | **Karelian pasty (bread)** |
| VALMISRUOKA LIHAPULLAT | Meatballs (ready_meals) | Meatballs (ready_meals) |
| ATERIA KANAKASTIKE | Chicken sauce / stew (ready_meals) | Chicken stew / meal (ready_meals) |
| TÄYSMEHU OMENA 1L | Apple juice (beverages) | Apple juice (beverages) |
| APPELSIINIMEHU | Orange juice (beverages) | Orange juice (beverages) |
| RUSINA 250G | Raisins (pantry) | Raisin (pantry) |

**Merge gate with the catalog on: holds** on both after-runs. On the 49-line fixture lines (49),
generic names (49) and categories (41 against 40) are not below baseline; sl (41, 41) is above
the baseline minimum of 39 and os (19, 20) above its minimum of 18, so neither is near the
floor of 37 and 16. Every watch-list mapping reads as specified. The catalog block costs 286
characters here (4431 -> 4717 on main, 4839 -> 5125 with the glossary), and main's first run
was a slow outlier (95.8 s).

One thing the empty-catalog runs could not show: **on main, the catalog silenced the short
receipt's shelf lives** - 1 and 3 of 9 with the catalog, against 9 of 9 without it. That is the
Q7 failure on a 9-line receipt, on the prompt production runs today. The glossary prompt's sl
clause (*"Estimate it for every food line, not only these"*) brings it back to 9 of 9 in both
runs, so H54 fixes that as a side effect. It is two runs on one synthetic receipt; a real short
receipt read with a warm catalog is the check worth making.

### The H53 live selection run

`tests/services/test_live_selection.py` puts the Q14 reported pairs to the real model through
`product_selection.select_products`, for the first time:

```
cd backend && LLM_BASE_URL=http://192.168.0.94:9292/v1 LLM_MODEL=c2.muse-glimmer \
  POSTGRES_DB=kyokki_a3 .venv/bin/python -m pytest tests/services/test_live_selection.py -m requires_vllm -v
```

| case | expected | before, run 1 | before, run 2 | after, run 1 | after, run 2 |
| --- | --- | --- | --- | --- | --- |
| ketchup-known | Ketchup | pass | pass | pass | pass |
| ketchup-new | null | pass | pass | pass | pass |
| melon | Melon | **null** | **null** | pass | pass |
| pear-juice | null | pass | pass | pass | pass |
| taco-shells-known | Taco shells | pass | pass | pass | pass |
| taco-shells-new | null | pass | pass | pass | pass |
| | | 5 of 6, 22.6 s | 5 of 6, 19.9 s | 6 of 6, 18.2 s | 6 of 6, 19.8 s |

The null cases H53's prompt was written for all hold. The one failure went the other way:
HUNAJAMELONI / *Honeydew* against a catalog *Melon* came back null in both runs, because
*"Different variety ... are DIFFERENT products"* reads as any variety. Two lines were added
after the Cherry tomato / Pineapple examples, with examples that are not the reported pairs
(`test_its_examples_are_not_the_reported_pairs` still holds):

```
But a kind of a food that a cook buys and uses the same way IS the same thing:
"Granny Smith" is "Apple", "Clementine" is "Mandarin".
```

Melon then passed in both runs and none of the null cases moved.

**The rule was then made one rule (2026-09-26).** Review of PR #99 pointed out that the added
lines contradicted the sentence directly above them (*"Different variety ... are DIFFERENT
products"*). The distinction is now stated once, as what a cook buys and uses differently:

```
What a cook buys and uses differently is a DIFFERENT product - plant milk vs dairy
milk, a different cut, a smaller or processed form:
- "Oat milk" is not "Milk". "Sour cream" is not "Cream". "Peanut butter" is not "Butter".
- "Cherry tomato" is not "Tomato". "Pineapple" is not "Apple".
A named kind of the same food, bought and used the same way, is the SAME product:
"Granny Smith" is "Apple", "Clementine" is "Mandarin".
```

| case | expected | reworded, run 1 | reworded, run 2 | reworded, run 3 |
| --- | --- | --- | --- | --- |
| ketchup-known | Ketchup | pass | pass | pass |
| ketchup-new | null | pass | pass | pass |
| melon | Melon | pass | pass | pass |
| pear-juice | null | pass | pass | pass |
| taco-shells-known | Taco shells | pass | pass | pass |
| taco-shells-new | null | pass | pass | pass |
| | | 6 of 6, 18.3 s | 6 of 6, 17.1 s | 6 of 6, 18.6 s |

First wording, no iteration needed. **Untested:** no reported pair is a variety that should stay
null, so the loosening towards "a named kind is the same" is not measured in that direction.
Pairs such as *Lactose-free milk* vs *Milk* (the prompt's own worked example, so it cannot be the
test), *Red onion* vs *Onion* or *Sweet potato* vs *Potato* would do it; adding one to
`reported_pairs.json` is the operator's call.


## Shelf lives that match the kitchen (Q19, 2026-09-26)

The fridge view on the iPad showed most of a fresh shop going stale two days after it was
bought. The estimator's examples were part of why: `minced beef -> d 2` and `banana -> d 7`
taught the model a fridge nobody has. The operator ruled on 2026-09-26 with reference numbers
counted from the day of purchase - packed minced beef 5, meat from the butcher's counter 3,
fish 3, banana 5, and tomatoes and oranges far longer than 5 - and those became the prompt's
examples in `catalog_estimates.INSTRUCTIONS`, with a line saying the numbers are for the usual
Finnish supermarket version, stored in its usual place, counted from the day of purchase. The
examples that did not conflict (sliced ham, salami, hard cheese, milk, crispbread, pasta,
onion) stayed. No plausibility band changed: every anchor already sat inside its category's.

Measured with `python -m scripts.measure_estimates` on the 31-product fixture
`tests/fixtures/shelf_life/estimate_products.json` (every anchor plus common Finnish staples),
`c2.muse-glimmer`, run sequentially: twice on `main`'s prompt from a scratch worktree at
`e71acff`, twice on the Q19 prompt. Gate: tomato ≥ 10, orange ≥ 14, banana 4-6, packed minced
beef 4-6, fish 2-4, butcher's-counter meat 2-4, and nothing dropped as out of band.

| product | gate | main, run 1 | main, run 2 | Q19, run 1 | Q19, run 2 |
| --- | --- | --- | --- | --- | --- |
| Minced beef (packed) | 4-6 | **2** fail | **2** fail | 5 | 5 |
| Beef steak from the butcher's counter | 2-4 | 3 | 3 | 3 | 3 |
| Salmon fillet | 2-4 | 2 | 2 | 3 | 3 |
| Banana | 4-6 | **7** fail | **7** fail | 5 | 5 |
| Tomato | ≥ 10 | 10 | 10 | 14 | 14 |
| Orange | ≥ 14 | 21 | 30 | 21 | 21 |
| dropped out of band / missing | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| answered, seconds | | 31 of 31, 62.5 s | 31 of 31, 72.4 s | 31 of 31, 72.6 s | 31 of 31, 72.9 s |

**The gate holds on both after-runs, at the first wording; no iteration was needed.** `main`
failed it on mince and banana in both runs - exactly the two examples the old prompt carried.

The rest of the fixture, for what else moved (Q19 runs):

```
Chicken fillet strips   3, 3   -> 5, 5      Apple         30, 30  -> 21, 21
Potato                 60, 60  -> 30, 30    Lemon         21, 30  -> 21, 21
Butter                 90, 90  -> 60, 60    Broccoli      10, 10  -> 7, 7
Karelian pie            5, 3   -> 7, 7      Rye bread      7, 7   -> 7, 10
Oat drink              90, 10  -> 10, 14    Orange juice  90, 180 -> 180, 30
Onion                  30, 90  -> 30, 30    Sour cream    21, 30  -> 21, 21
Yoghurt                21, 21  -> 21, 14
```

Unchanged in all four runs: Milk 7, Carrot 30, Cucumber 10, Lettuce 7, Eggs 28, Cheese 60,
Sliced ham 10, Sausage 30, Bell pepper 14, Grapes 14, Strawberries 5, Rice 720.

**The honest part.** The gated answers equal the examples, so this measures that the model
follows its anchors rather than that it knows mince - but following the anchors is the
behaviour the ruling asked for, and `main` did not have it. The anchors also pulled neighbours:
chicken fillet strips went from 3 to 5, the same as packed mince, which is plausible for a
sealed supermarket pack. Beverages still wander between runs (orange juice 180 then 30, oat
drink 10 then 14), as Q11 recorded; the dry run shows those before anything is saved.
