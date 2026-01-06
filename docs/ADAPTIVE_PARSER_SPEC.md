# Adaptive Receipt Parser — Specification

## Overview

The receipt parser should handle any store format, not just pre-configured Finnish chains. When encountering an unknown receipt format, the system analyzes it, extracts products, and optionally learns a reusable template for future receipts from that store.

## Design Goals

1. **Zero-config for users** — No manual template creation required
2. **Fast for known formats** — Template-based parsing (no LLM) for recognized stores
3. **Graceful unknown handling** — LLM fallback extracts products from any receipt
4. **Learning over time** — New store formats become "known" after confirmation
5. **User corrections improve accuracy** — Feedback loop refines templates

---

## Architecture

```
Receipt Image/PDF
       │
       ▼
┌──────────────────┐
│  Text Extraction │  PDF → pdfplumber, Image → MinerU OCR
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Store Detection  │  Match header against known store patterns
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
 Known     Unknown
    │         │
    ▼         ▼
┌────────┐  ┌─────────────────┐
│Template│  │ LLM Extraction  │
│ Parse  │  │ (Ollama/Claude) │
└───┬────┘  └────────┬────────┘
    │                │
    │         ┌──────┴──────┐
    │         │             │
    │     Products    Template Suggestion
    │         │             │
    │         ▼             ▼
    │    ┌─────────┐   ┌──────────┐
    │    │ Review  │   │  Store   │
    │    │ Screen  │   │  Config  │
    │    └────┬────┘   │ (if user │
    │         │        │ confirms)│
    └────┬────┘        └──────────┘
         │
         ▼
    ┌─────────┐
    │Inventory│
    └─────────┘
```

---

## Store Configuration Model

### Database Schema

```sql
CREATE TABLE store_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identification
    name VARCHAR(100) NOT NULL,              -- "K-market", "Whole Foods", "Aldi"
    chain VARCHAR(100),                       -- Parent chain if applicable
    country VARCHAR(2),                       -- ISO 3166-1 alpha-2
    language VARCHAR(5),                      -- ISO 639-1 (or 639-1-region like "en-US")
    currency VARCHAR(3),                      -- ISO 4217
    
    -- Detection patterns (any match = this store)
    detection_patterns JSONB NOT NULL,        -- ["K-market", "K-MARKET", "Kesko"]
    
    -- Parsing configuration
    parser_type VARCHAR(20) DEFAULT 'template', -- 'template', 'llm_only', 'hybrid'
    parser_config JSONB,                      -- Template rules (see below)
    
    -- Learning metadata
    confidence FLOAT DEFAULT 0.5,             -- How reliable is this config
    sample_count INTEGER DEFAULT 0,           -- Receipts parsed with this config
    last_used TIMESTAMP,
    
    -- Source
    source VARCHAR(20) DEFAULT 'learned',     -- 'builtin', 'learned', 'user'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast pattern matching
CREATE INDEX idx_store_detection ON store_config USING GIN (detection_patterns);
```

### Parser Config Structure

```json
{
  "version": 1,
  
  "locale": {
    "country": "FI",
    "languages": ["fi", "sv", "en"],
    "decimal_separator": ",",
    "thousand_separator": " ",
    "currency": "EUR",
    "currency_symbols": ["€", "EUR"]
  },
  
  "line_rules": {
    "product_pattern": "^(.+?)\\s+(\\d+[,.]\\d{2})\\s*[A-Z]?$",
    "product_name_group": 1,
    
    "quantity_patterns": [
      {
        "pattern": "^\\s*(\\d+)\\s*(?:KPL|pcs|st|Stk|szt)",
        "type": "count",
        "group": 1
      },
      {
        "pattern": "(\\d+[,.]\\d+)\\s*(?:kg|KG)\\s*[x×*]",
        "type": "weight_kg",
        "group": 1
      },
      {
        "pattern": "(\\d+[,.]\\d+)\\s*(?:l|L|lt)\\s*[x×*]",
        "type": "volume_l",
        "group": 1
      }
    ],
    
    "skip_patterns": [
      "^TOTAL", "^SUMMA", "^YHTEENSÄ", "^GESAMT", "^SUMA",
      "^TAX", "^VAT", "^ALV", "^MwSt", "^TVA",
      "^SUBTOTAL", "^ZWISCHENSUMME",
      "deposit", "pfand", "pantti", "pant"
    ]
  },
  
  "structure": {
    "header_ends_at": ["---", "========", "RECEIPT", "KUITTI", "KASSENBON"],
    "footer_starts_at": ["TOTAL", "SUMMA", "YHTEENSÄ", "GESAMT"],
    "quantity_line_position": "next_line"
  }
}
```

**Locale-aware patterns:**
- Quantity words: `KPL` (FI), `pcs` (EN), `st` (SV), `Stk` (DE), `szt` (PL)
- Total words: `TOTAL` (EN), `YHTEENSÄ` (FI), `GESAMT` (DE), `SUMA` (ES/PL)
- Deposit words: `deposit` (EN), `pantti` (FI), `Pfand` (DE), `pant` (SV/NO/DK)
- Tax: `VAT`, `TAX`, `ALV` (FI), `MwSt` (DE), `TVA` (FR)

---

## Detection Flow

### Step 1: Text Extraction

```python
async def extract_text(file_path: str) -> str:
    if file_path.endswith('.pdf'):
        return extract_pdf_text(file_path)  # pdfplumber
    return await mineru_ocr(file_path)
```

### Step 2: Store Detection

```python
async def detect_store(text: str, db: AsyncSession) -> StoreConfig | None:
    """
    Try to match receipt text against known store patterns.
    Returns None if no confident match.
    """
    # Get first ~500 chars (header area)
    header = text[:500].upper()
    
    # Query stores where any detection pattern matches
    stores = await db.execute(
        select(StoreConfig).where(
            StoreConfig.detection_patterns.op('?|')(
                extract_potential_patterns(header)
            )
        )
    )
    
    matches = stores.scalars().all()
    
    if not matches:
        return None
    
    # Score matches by pattern specificity and confidence
    best = max(matches, key=lambda s: score_match(s, header))
    
    if best.confidence > 0.3:  # Minimum threshold
        return best
    
    return None


def extract_potential_patterns(header: str) -> list[str]:
    """Extract words/phrases that might identify the store."""
    # Common store name patterns
    words = re.findall(r'\b[A-ZÄÖÅ][A-ZÄÖÅ0-9\-]{2,20}\b', header)
    return words
```

### Step 3: Parse or Analyze

```python
async def parse_receipt(text: str, db: AsyncSession) -> ParseResult:
    store = await detect_store(text, db)
    
    if store and store.parser_type == 'template':
        # Fast path: use stored template
        result = template_parse(text, store.parser_config)
        result.store_config_id = store.id
        return result
    
    elif store and store.parser_type == 'hybrid':
        # Try template, fall back to LLM if low confidence
        result = template_parse(text, store.parser_config)
        if result.confidence > 0.7:
            return result
        # Fall through to LLM
    
    # Unknown store or low confidence: use LLM
    return await llm_parse(text, store_hint=store)
```

---

## LLM Extraction

### Extraction Prompt (Language-Agnostic)

```python
LLM_EXTRACT_PROMPT = """
Analyze this grocery store receipt and extract the products.

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

Also identify:
- store_name: The store name from the header
- store_chain: Parent chain if identifiable
- country: Country code (ISO 3166-1 alpha-2)
- language: Primary language of receipt (ISO 639-1)
- currency: Currency code (ISO 4217)

Respond in JSON:
{
  "store": {
    "name": "...",
    "chain": "...",
    "country": "FI",
    "language": "fi",
    "currency": "EUR"
  },
  "products": [
    {
      "name": "Maito 1L",
      "name_en": "Milk 1L",
      "quantity": 1,
      "weight_kg": null,
      "unit": "pcs"
    }
  ]
}

Important:
- Preserve original product names (don't translate the name field)
- Recognize quantity words in any language (pcs, KPL, Stk, st, szt, шт, 個)
- Recognize weight/volume units (kg, g, l, ml, oz, lb)
- Handle various decimal separators (. or ,)
- Skip totals, tax lines, deposits regardless of language
"""
```

### Template Generation Prompt (Language-Aware)

```python
LLM_TEMPLATE_PROMPT = """
Based on this receipt, create parsing rules for future receipts from this store.

Receipt text:
```
{receipt_text}
```

Receipt metadata:
- Country: {country}
- Language: {language}
- Currency: {currency}

Extracted products (confirmed correct):
{products_json}

Generate a parser configuration that:
1. Works for this store's specific format
2. Uses patterns appropriate for the receipt's language
3. Includes common skip words in that language (total, tax, deposit, etc.)

Include in skip_patterns the local language words for:
- Total/Sum (e.g., TOTAL, YHTEENSÄ, GESAMT, SUMA, 合計)
- Tax/VAT (e.g., TAX, VAT, ALV, MwSt, TVA, 税)
- Subtotal
- Deposit/Bottle return
- Payment method lines

Respond in JSON matching this schema:
{schema}
"""
```

---

## Learning Flow

### After Successful LLM Parse

```python
async def handle_receipt_confirmation(
    receipt_id: UUID,
    confirmed_items: list[ConfirmedItem],
    db: AsyncSession
):
    receipt = await get_receipt(receipt_id)
    
    # If this was an LLM parse and user confirmed items...
    if receipt.parse_method == 'llm' and len(confirmed_items) > 3:
        
        # Check if we should learn this store
        store = await detect_store(receipt.ocr_text, db)
        
        if store is None:
            # Completely new store - offer to learn
            await queue_template_learning(receipt, confirmed_items)
        
        elif store.source == 'learned' and store.confidence < 0.8:
            # Existing learned store - reinforce or correct
            await update_store_confidence(store, confirmed_items)
```

### Template Learning Task

```python
@celery_app.task
async def learn_store_template(receipt_id: UUID, confirmed_items: list):
    receipt = await get_receipt(receipt_id)
    
    # Ask LLM to generate template
    template = await llm_generate_template(
        receipt.ocr_text,
        confirmed_items
    )
    
    # Validate template by re-parsing the same receipt
    test_result = template_parse(receipt.ocr_text, template)
    
    if test_result.matches_confirmed(confirmed_items, threshold=0.8):
        # Template works - save it
        store_config = StoreConfig(
            name=template['store_name'],
            detection_patterns=template['detection_patterns'],
            parser_type='template',
            parser_config=template['parser_config'],
            source='learned',
            confidence=0.5,  # Start conservative
            sample_count=1
        )
        await db.add(store_config)
        
        # Link receipt to this config
        receipt.store_config_id = store_config.id
        await db.commit()
```

---

## Confidence & Reinforcement

### Confidence Score Updates

```python
async def update_store_confidence(
    store: StoreConfig,
    confirmed_items: list[ConfirmedItem],
    parse_result: ParseResult
):
    """
    Adjust confidence based on how well parsing matched user confirmation.
    """
    # Calculate match rate
    matched = sum(1 for item in parse_result.items 
                  if item in confirmed_items)
    match_rate = matched / len(confirmed_items) if confirmed_items else 0
    
    # Exponential moving average
    alpha = 0.2  # Learning rate
    store.confidence = (1 - alpha) * store.confidence + alpha * match_rate
    store.sample_count += 1
    store.last_used = datetime.utcnow()
    
    # If confidence drops too low, flag for re-learning
    if store.confidence < 0.3 and store.sample_count > 5:
        store.parser_type = 'hybrid'  # Add LLM fallback
```

### When to Re-learn

```python
async def maybe_relearn_template(store: StoreConfig, receipt: Receipt):
    """
    Trigger template re-learning if:
    - Confidence dropped below threshold
    - Haven't seen this store in a while (format may have changed)
    - Multiple recent parse failures
    """
    should_relearn = (
        store.confidence < 0.4 or
        (store.last_used and 
         datetime.utcnow() - store.last_used > timedelta(days=180))
    )
    
    if should_relearn and store.source == 'learned':
        await queue_template_learning(receipt)
```

---

## Built-in Templates

Ship with pre-configured templates for common stores. Community can contribute more.

```python
BUILTIN_STORES = [
    # Finnish
    {
        "name": "Prisma",
        "chain": "S-Group",
        "country": "FI",
        "language": "fi",
        "currency": "EUR",
        "detection_patterns": ["S-KAUPAT", "Prisma", "HOK-ELANTO"],
        "source": "builtin",
        "confidence": 0.9,
        "parser_config": { ... }
    },
    {
        "name": "K-market",
        "chain": "Kesko",
        "country": "FI",
        "language": "fi",
        "currency": "EUR",
        "detection_patterns": ["K-market", "K-MARKET", "Kesko"],
        "source": "builtin",
        "confidence": 0.9,
        "parser_config": { ... }
    },
    # German
    {
        "name": "Aldi Süd",
        "chain": "Aldi",
        "country": "DE",
        "language": "de",
        "currency": "EUR",
        "detection_patterns": ["ALDI", "Aldi Süd"],
        "source": "builtin",
        "confidence": 0.9,
        "parser_config": { ... }
    },
    # US
    {
        "name": "Walmart",
        "chain": "Walmart",
        "country": "US",
        "language": "en",
        "currency": "USD",
        "detection_patterns": ["WALMART", "Walmart"],
        "source": "builtin",
        "confidence": 0.9,
        "parser_config": { ... }
    },
    # ... community contributions welcome
]
```

On first run, seed these into `store_config` table. Users can disable built-ins they don't use.

### Common Skip Patterns by Language

```python
SKIP_PATTERNS_BY_LANGUAGE = {
    "en": ["TOTAL", "SUBTOTAL", "TAX", "VAT", "CHANGE", "CASH", "CARD", "DEPOSIT"],
    "fi": ["YHTEENSÄ", "VÄLISUMMA", "ALV", "VERO", "PANTTI", "KORTTI"],
    "de": ["GESAMT", "SUMME", "MwSt", "STEUER", "PFAND", "KARTE", "BAR"],
    "sv": ["TOTALT", "SUMMA", "MOMS", "PANT", "KORT"],
    "fr": ["TOTAL", "SOUS-TOTAL", "TVA", "TAXE", "CONSIGNE", "CARTE"],
    "es": ["TOTAL", "SUBTOTAL", "IVA", "IMPUESTO", "TARJETA"],
    "pl": ["SUMA", "RAZEM", "VAT", "PODATEK", "KARTA"],
    "nl": ["TOTAAL", "SUBTOTAAL", "BTW", "STATIEGELD", "PIN"],
}

# Used when generating templates for new stores
def get_skip_patterns(language: str) -> list[str]:
    base = SKIP_PATTERNS_BY_LANGUAGE.get("en", [])  # English as fallback
    local = SKIP_PATTERNS_BY_LANGUAGE.get(language, [])
    return list(set(base + local))
```

---

## API Endpoints

### Get Store Configs

```
GET /api/stores
```

Returns list of known store configurations with confidence scores.

### Manual Store Config

```
POST /api/stores
{
  "name": "My Local Shop",
  "detection_patterns": ["MY LOCAL", "Local Shop"],
  "parser_config": { ... }  // Optional - will use LLM if not provided
}
```

### Trigger Re-learning

```
POST /api/stores/{id}/relearn
{
  "receipt_id": "uuid"  // Use this receipt as training example
}
```

---

## UI Flow

### Unknown Store Receipt

1. User scans receipt
2. System shows: "New store detected: **Whole Foods**"
3. LLM extracts products, shows review screen
4. User confirms/corrects items
5. System asks: "Save this store for faster future scanning?"
6. If yes: template learned and stored

### Low Confidence Parse

1. User scans receipt from "learned" store
2. Template parse has low confidence
3. System automatically falls back to LLM
4. Shows review screen with note: "Double-check these items"
5. User confirmation reinforces or corrects the template

---

## Fallback Hierarchy

```
1. Exact template match (confidence > 0.7)
   └─→ Use template parser
   
2. Template match with low confidence (0.3 - 0.7)
   └─→ Template parse + LLM verification
   
3. Store detected but no template
   └─→ LLM extraction, offer to learn template
   
4. Unknown store
   └─→ LLM extraction, offer to create store config

5. LLM fails or unavailable
   └─→ Show raw OCR text, manual product entry
```

---

## Performance Considerations

| Scenario | Latency | Cost |
|----------|---------|------|
| Known store, template parse | ~100ms | None |
| Hybrid (template + LLM verify) | ~3-5s | 1 LLM call |
| Unknown store, LLM extract | ~5-10s | 1-2 LLM calls |
| Template learning | ~10-15s | 2-3 LLM calls (async) |

Template parsing should be the common case after initial learning period.

---

## Testing Strategy

### Template Parser Tests
- Test each built-in template against sample receipts
- Verify extraction accuracy > 95%

### LLM Extraction Tests
- Test with diverse receipt formats (US, EU, Asian)
- Verify reasonable extraction from unknown formats

### Learning Tests
- Confirm template generation produces valid config
- Verify learned template parses original receipt correctly
- Test confidence updates work as expected

### Integration Tests
- Full flow: unknown receipt → LLM → confirm → learned → template parse
