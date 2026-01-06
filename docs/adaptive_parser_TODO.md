# Adaptive Receipt Parser — Development TODO

**Spec:** [ADAPTIVE_PARSER_SPEC.md](./ADAPTIVE_PARSER_SPEC.md)

---

## 🎯 Current Status

**✅ Phase 1: LLM Fallback (COMPLETE - Sprint 3A)**
- vLLM integration with language-agnostic extraction
- Pydantic models for structured data validation
- 27 comprehensive tests with multi-language support
- Pure LLM approach working end-to-end

**📍 Next: Sprint 3B Integration**
- Wire LLM extraction into Receipt API
- Add fuzzy matching to product_master
- Async processing with Celery

**🔜 Future: Template Optimization**
- Store detection and template parser (Phase 1: Foundation)
- Template learning from confirmed receipts (Phase 2)
- Confidence tracking and optimization

---

## Overview

Replace hardcoded store parsers with adaptive system that:
1. Uses templates for known stores (fast)
2. Falls back to LLM for unknown stores
3. Learns new templates from confirmed extractions
4. **Works with any language/country** — no hardcoded Finnish assumptions

**Current MVP Strategy:** Pure LLM approach first, optimize with templates later.

---

## Phase 1: Foundation

### Database

- [ ] `store_config` table
  ```sql
  CREATE TABLE store_config (
      id UUID PRIMARY KEY,
      name VARCHAR(100) NOT NULL,
      chain VARCHAR(100),
      country VARCHAR(2),              -- ISO 3166-1 alpha-2
      language VARCHAR(5),             -- ISO 639-1
      currency VARCHAR(3),             -- ISO 4217
      detection_patterns JSONB NOT NULL,
      parser_type VARCHAR(20) DEFAULT 'template',
      parser_config JSONB,
      confidence FLOAT DEFAULT 0.5,
      sample_count INTEGER DEFAULT 0,
      last_used TIMESTAMP,
      source VARCHAR(20) DEFAULT 'learned',
      created_at TIMESTAMP DEFAULT NOW()
  );
  ```
- [ ] GIN index on `detection_patterns` for fast matching
- [ ] Migration script
- [ ] Seed built-in stores (Finnish + common international)

### Locale Support

- [ ] `SKIP_PATTERNS_BY_LANGUAGE` — common skip words per language
  ```python
  {
      "en": ["TOTAL", "SUBTOTAL", "TAX", "VAT", "DEPOSIT"],
      "fi": ["YHTEENSÄ", "ALV", "PANTTI"],
      "de": ["GESAMT", "MwSt", "PFAND"],
      "sv": ["TOTALT", "MOMS", "PANT"],
      # ... more languages
  }
  ```
- [ ] `QUANTITY_WORDS` — piece/unit words per language
  ```python
  ["pcs", "KPL", "st", "Stk", "szt", "шт", "個", "件"]
  ```
- [ ] Decimal separator handling (`,` vs `.`)
- [ ] Currency symbol recognition

### Store Detection

- [ ] `detect_store(text: str) -> StoreConfig | None`
  - Extract header (first 500 chars)
  - Query `store_config` for pattern matches
  - Return best match above confidence threshold
  - Return `None` if no match

### Template Parser Engine

- [ ] `TemplateParser` class
  ```python
  class TemplateParser:
      def __init__(self, config: dict):
          self.config = config
          self._compile_patterns()
      
      def parse(self, text: str) -> list[ParsedItem]:
          # Apply line rules, skip patterns, etc.
          pass
  ```
- [ ] Support for parser_config schema:
  - `product_pattern` — regex for product lines
  - `quantity_patterns` — list of quantity/weight patterns
  - `skip_patterns` — lines to ignore
  - `structure.quantity_line_position` — same_line, next_line, indented

### Built-in Templates

- [ ] S-Group template (from actual receipt analysis)
- [ ] K-Group template
- [ ] Lidl template
- [ ] Seed script to insert on first run

---

## ✅ Phase 1: LLM Fallback (COMPLETE - Sprint 3A)

### LLM Client

- [x] `extract_products_from_receipt(text: str) -> ReceiptExtraction` — ✅ Implemented in `services/llm_extractor.py`
  ```python
  class ReceiptExtraction(BaseModel):
      store: StoreInfo               # Store name, chain, country, language, currency
      products: list[ParsedProduct]  # Extracted products with quantities/weights
      confidence: float              # Extraction confidence score
  ```

### Extraction Prompt (Language-Agnostic)

- [x] Design prompt that:
  - [x] Works with any language receipt — ✅ Language-agnostic extraction
  - [x] Preserves original product names — ✅ `name` field in original language
  - [x] Identifies language, country, currency — ✅ StoreInfo model
  - [x] Recognizes quantity words in multiple languages — ✅ Handled in prompt
  - [x] Handles various decimal separators — ✅ Handled in prompt
- [x] Test with diverse receipts:
  - [x] Finnish (S-Group, K-Group, Lidl) — ✅ Multi-language tests
  - [ ] German (Aldi, Lidl DE, Rewe) — Not tested yet
  - [ ] US (Walmart, Whole Foods, Kroger) — Not tested yet
  - [ ] UK (Tesco, Sainsbury's) — Not tested yet
  - [ ] Other EU (Carrefour, Albert Heijn) — Not tested yet

### Fallback Flow

- [ ] Update `parse_receipt()` with template-first approach:
  ```python
  async def parse_receipt(text: str) -> ParseResult:
      store = await detect_store(text)

      if store and store.confidence > 0.7:
          return template_parse(text, store)

      # LLM fallback
      result = await llm_extract_products(text)
      result.parse_method = 'llm'
      result.store_hint = store
      return result
  ```
  **Note**: Currently using pure LLM approach. Template optimization deferred to Phase 1: Foundation.

---

## Phase 2: Template Learning

### Learning Trigger

- [ ] After receipt confirmation, check if learning needed:
  ```python
  async def on_receipt_confirmed(receipt_id, confirmed_items):
      receipt = await get_receipt(receipt_id)
      
      if receipt.parse_method == 'llm' and len(confirmed_items) >= 3:
          await maybe_learn_template(receipt, confirmed_items)
  ```

### Template Generation

- [ ] `generate_template_from_receipt(text, products) -> dict`
  - Use LLM to analyze pattern and generate parser_config
  - Prompt includes: receipt text, confirmed products, target schema

- [ ] Template validation:
  - Re-parse original receipt with generated template
  - Compare against confirmed products
  - Only save if match rate > 80%

### Celery Task

- [ ] `learn_store_template.delay(receipt_id, confirmed_items)`
  - Async task (don't block user)
  - Generate template
  - Validate template
  - Save to `store_config` if valid
  - Update receipt with `store_config_id`

### User Prompt

- [ ] Frontend: "Save this store for faster scanning?"
  - Show after successful LLM parse + confirmation
  - Optional — don't force users to engage

---

## Phase 2: Confidence & Reinforcement

### Confidence Updates

- [ ] `update_store_confidence(store, parse_result, confirmed_items)`
  - Calculate match rate between parsed and confirmed
  - Exponential moving average update
  - Increment `sample_count`
  - Update `last_used`

### Automatic Fallback

- [ ] If `confidence < 0.5`, switch `parser_type` to `hybrid`
  - Template parse first
  - LLM verification if template confidence low
  - User sees: "Please double-check these items"

### Re-learning Trigger

- [ ] Conditions for re-learning:
  - `confidence < 0.4` after 5+ samples
  - Store not seen in 180+ days
  - User explicitly requests re-learn

- [ ] `POST /api/stores/{id}/relearn` endpoint

---

## Phase 3: API & Admin

### Endpoints

- [ ] `GET /api/stores` — list all store configs
  ```json
  [
    {
      "id": "uuid",
      "name": "Prisma",
      "chain": "S-Group",
      "confidence": 0.92,
      "sample_count": 47,
      "source": "builtin"
    }
  ]
  ```

- [ ] `POST /api/stores` — manually add store config
  ```json
  {
    "name": "My Local Shop",
    "detection_patterns": ["LOCAL SHOP", "My Local"],
    "parser_config": {}  // Optional
  }
  ```

- [ ] `DELETE /api/stores/{id}` — remove learned store

- [ ] `POST /api/stores/{id}/relearn` — trigger re-learning

### Admin UI (Optional)

- [ ] View store configs with confidence scores
- [ ] Edit detection patterns
- [ ] Test parser against sample text
- [ ] View parse history per store

---

## Testing

### Unit Tests

- [ ] Template parser with various configs
- [ ] Store detection with multiple patterns
- [ ] Confidence score calculations

### Integration Tests

- [ ] Full flow: unknown store → LLM → confirm → learn → template
- [ ] Hybrid mode fallback
- [ ] Re-learning trigger

### Receipt Samples

- [ ] Collect diverse receipts for testing:
  
  **Finnish (provided):**
  - S-Group (Prisma) ✓
  - K-Group (K-market) ✓
  - Lidl FI ✓
  
  **German:**
  - Aldi
  - Lidl DE
  - Rewe
  - Edeka
  
  **US:**
  - Walmart
  - Whole Foods
  - Kroger
  - Target
  
  **UK:**
  - Tesco
  - Sainsbury's
  - Aldi UK
  
  **Other EU:**
  - Carrefour (FR)
  - Albert Heijn (NL)
  - ICA (SE)
  
  **Challenging formats:**
  - Non-Latin scripts (Russian, Japanese, Chinese)
  - Mixed language receipts
  - Abbreviated product names
  - Thermal receipt photos (degraded quality)

---

## File Structure

```
backend/app/
├── parsers/
│   ├── __init__.py
│   ├── base.py              # ParsedItem, ParseResult
│   ├── detector.py          # detect_store()
│   ├── template_engine.py   # TemplateParser class
│   ├── llm_extractor.py     # LLM extraction
│   └── learner.py           # Template learning
├── models/
│   └── store_config.py      # StoreConfig model
├── services/
│   └── receipt_service.py   # Updated to use adaptive parser
└── tasks/
    └── learning_tasks.py    # Template learning Celery task
```

---

## Migration from Hardcoded Parsers

### Before
```
parsers/
├── sgroup.py    # Hardcoded S-Group rules
├── kgroup.py    # Hardcoded K-Group rules
└── lidl.py      # Hardcoded Lidl rules
```

### After
```
store_config table:
├── S-Group (builtin, parser_config from sgroup.py)
├── K-Group (builtin, parser_config from kgroup.py)
├── Lidl (builtin, parser_config from lidl.py)
└── [learned stores added over time]
```

- [ ] Convert existing parser logic to `parser_config` JSON
- [ ] Create seed data from converted configs
- [ ] Remove hardcoded parser files
- [ ] Update receipt processing to use `detect_store()` + `TemplateParser`

---

## Priority

| Task | Priority | Phase |
|------|----------|-------|
| store_config table | High | 1 |
| Template parser engine | High | 1 |
| Store detection | High | 1 |
| Convert Finnish stores to templates | High | 1 |
| LLM extraction fallback | High | 1 |
| Template learning | Medium | 2 |
| Confidence tracking | Medium | 2 |
| Re-learning | Low | 2 |
| Admin API | Low | 3 |

---

## Decisions

**LLM for learning, not runtime** — Template parsing is fast. LLM is slow. Use LLM to *generate* templates, then use templates at runtime. LLM fallback only for truly unknown stores.

**Confidence threshold 0.7** — Below this, add LLM verification. Below 0.3, don't trust template at all.

**Minimum 3 products to learn** — Don't create templates from tiny receipts.

**Async learning** — Template generation happens in background. User gets their inventory immediately from LLM parse.

**Language-agnostic by design** — No hardcoded language assumptions in core parser. All language-specific patterns stored in `parser_config` or `SKIP_PATTERNS_BY_LANGUAGE` lookup tables. LLM handles unknown languages automatically.

**Preserve original product names** — Don't translate product names in database. User sees what's on the receipt. Optional `name_en` field for search/matching purposes.
