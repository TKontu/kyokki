# Infrastructure & AI/ML — Development TODO

---

## 🎯 Current Status

**✅ Docker Infrastructure** (Partial)
- Docker Compose configured with backend, PostgreSQL, Redis, Celery
- Backend volume mounts for development
- Environment variable configuration

**✅ OCR Pipeline** (Sprint 3A Complete)
- PDF text extraction with pdfplumber
- MinerU OCR integration for images
- File type routing implemented

**✅ Receipt Extraction** (Sprint 3A Complete)
- vLLM-based language-agnostic extraction
- Replaces hardcoded store parsers with LLM approach
- Works with any store/language

**⏳ Pending**
- Traefik SSL setup
- Product matching implementation (RapidFuzz)
- Celery task integration

---

## Infrastructure

### Docker Compose

```yaml
services:
  traefik:
    image: traefik:v3.0
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik:/etc/traefik

  frontend:
    build: ./frontend
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.frontend.rule=Host(`fridge.local`)"

  api:
    build: ./backend
    labels:
      - "traefik.http.routers.api.rule=PathPrefix(`/api`)"
    depends_on: [postgres, redis]

  celery-worker:
    build: ./backend
    command: celery -A app.tasks worker -l info

  postgres:
    image: postgres:15-alpine
    volumes: [postgres_data:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
```

### Tasks
- [x] Docker Compose (dev + prod overrides) — ✅ Basic setup complete, Traefik commented out
- [ ] Traefik SSL (self-signed or mkcert)
- [ ] Volume structure: `./data/images/receipts/`, `./data/backups/`
- [ ] Backup script (pg_dump, cron)
- [ ] Makefile (dev, prod, logs, shell, backup, migrate)

---

## OCR Pipeline

### ✅ File Type Routing (Sprint 3A Complete)
PDFs (S-Group digital receipts) don't need OCR — extract text directly.

```python
# Implemented in app/services/ocr_service.py
async def extract_text_from_receipt(file_path: str, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return extract_text_from_pdf(file_path)  # pdfplumber
    else:
        return await extract_text_from_image(file_path)  # MinerU API
```

- [x] PDF text extraction (pdfplumber) — ✅ `extract_text_from_pdf()`
- [x] Image OCR (MinerU client) — ✅ `extract_text_from_image()`
- [x] File type routing — ✅ Implemented with MIME type detection

### ✅ MinerU Integration (Sprint 3A Complete)
```python
# Implemented in app/services/ocr_service.py
async def extract_text_from_image(file_path: str) -> str:
    async with httpx.AsyncClient(timeout=settings.MINERU_TIMEOUT) as client:
        response = await client.post(
            f"{settings.MINERU_BASE_URL}/parse",
            files={"file": ...},
            data={"parse_method": "auto"}
        )
        return response.json()["content"]
```

- [x] MinerU client — ✅ HTTP client with timeout configuration
- [x] Error handling + retry — ✅ HTTPError handling

### ✅ Adaptive LLM Extraction (Sprint 3A Complete)

**Approach:** Instead of hardcoded store parsers, we use vLLM for language-agnostic extraction.

```python
# Implemented in app/services/llm_extractor.py
async def extract_products_from_receipt(ocr_text: str) -> ReceiptExtraction:
    """Extract structured product data using vLLM."""
    # Language-agnostic prompt that:
    # - Identifies store, chain, country, language, currency
    # - Extracts products with quantities, weights, volumes, prices
    # - Skips totals, discounts, deposits automatically
    # - Works with ANY language/store format
```

**Benefits over hardcoded parsers:**
- ✅ Works with any store (S-Group, K-Group, Lidl, international stores)
- ✅ Language-agnostic (Finnish, English, German, Swedish, etc.)
- ✅ Handles variations in receipt formats automatically
- ✅ No maintenance needed for new store formats
- ✅ Extracts store metadata (name, chain, country, language, currency)

**Pydantic Models:**
```python
class ParsedProduct(BaseModel):
    name: str              # Original language
    name_en: str | None    # English translation
    quantity: float
    weight_kg: float | None
    volume_l: float | None
    unit: str              # pcs, kg, l, unit
    price: float | None

class StoreInfo(BaseModel):
    name: str | None       # e.g., "Prisma Jyväskylä"
    chain: str | None      # e.g., "s-group"
    country: str | None    # ISO 3166-1 alpha-2
    language: str | None   # ISO 639-1
    currency: str | None   # ISO 4217
```

- [x] LLM extraction client — ✅ vLLM with OpenAI-compatible API
- [x] Language-agnostic prompt — ✅ Works with any language
- [x] Store detection — ✅ Automatic from LLM output
- [x] Product extraction — ✅ With quantities, weights, volumes
- [x] Tests with actual receipts — ✅ Multi-language test suite

**🔜 Future:** Template optimization for known stores (see adaptive_parser_TODO.md)

---

## Product Matching

### Matching Strategy
```
Receipt Text → Exact Alias Match → Fuzzy Match → OFF Lookup → Ollama → Manual
```

### Fuzzy Matching
```python
from rapidfuzz import fuzz, process

def match(query: str, candidates: list[str], threshold=80):
    matches = process.extract(query, candidates, scorer=fuzz.token_sort_ratio)
    return [m for m in matches if m[1] >= threshold]
```

- [ ] RapidFuzz integration
- [ ] Normalization (lowercase, remove units like "kpl", "kg")
- [ ] Confidence scoring

---

## Open Food Facts Integration

```python
class OFFClient:
    BASE_URL = "https://world.openfoodfacts.org/api/v2/product"
    
    async def lookup(self, barcode: str) -> dict | None:
        resp = await self.client.get(f"{self.BASE_URL}/{barcode}")
        if resp.status_code == 200:
            return resp.json().get("product")
        return None
```

**Data to extract:**
- product_name (prefer user's language)
- brands
- categories → map to system categories
- image_url
- nutriscore_grade
- nutriments

- [ ] OFF client
- [ ] Response caching (store in product_master.off_data)
- [ ] Category mapping
- [ ] Graceful fallback on miss

---

## GS1 DataMatrix Parsing

```python
def parse_gs1(data: str) -> dict:
    """Parse GS1 element string."""
    result = {}
    # AI patterns: (01) GTIN, (17) expiry, (10) batch, (310x) weight
    # Example: ]d201034531200000211712310010ABC123
    # → GTIN: 03453120000021, Expiry: 2031-12-17, Batch: ABC123
    
    # Use FNC1 separator (ASCII 29) or fixed lengths
    pass
```

- [ ] GS1 AI parser
- [ ] Date parsing (YYMMDD → date, handle century)
- [ ] Weight parsing (variable decimal point)
- [ ] Integration with scanner input

---

## ✅ vLLM Receipt Extraction (Sprint 3A Complete)

**Replaced Ollama fallback with primary vLLM extraction.**

```python
# Implemented in app/services/llm_extractor.py
async def extract_products_from_receipt(ocr_text: str) -> ReceiptExtraction:
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            json={
                "model": settings.LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": settings.LLM_TEMPERATURE,
                "max_tokens": 16384
            }
        )
```

- [x] vLLM client — ✅ OpenAI-compatible API
- [x] Receipt extraction prompt — ✅ Language-agnostic, structured output
- [x] Store and product identification — ✅ Automatic extraction
- [x] Error handling — ✅ HTTPError and validation errors

---

## Celery Tasks

```python
@celery_app.task
def process_receipt(receipt_id: str):
    receipt = get_receipt(receipt_id)
    
    # 1. OCR
    text = mineru.extract_text(receipt.image_path)
    
    # 2. Parse
    parser = detect_parser(text)
    items = parser.parse(text)
    
    # 3. Match
    matched = [match_product(item) for item in items]
    
    # 4. Save + notify
    save_results(receipt_id, matched)
    broadcast_complete(receipt_id)
```

- [ ] Receipt processing task
- [ ] Stock check task (after consumption)
- [ ] Scheduled expiry check (Celery beat, daily)

---

## Environment Variables

```env
# Infrastructure
POSTGRES_HOST=postgres
POSTGRES_PASSWORD=xxx
REDIS_HOST=redis

# OCR (Sprint 3A - Implemented)
MINERU_BASE_URL=http://192.168.0.xxx:8000
MINERU_TIMEOUT=300.0
MINERU_PARSE_METHOD=auto

# vLLM (Sprint 3A - Implemented)
LLM_BASE_URL=http://192.168.0.xxx:8000
LLM_API_KEY=token-abc123
LLM_MODEL=Qwen3-4B-Instruct
LLM_TEMPERATURE=0.1

# Matching (Pending - Sprint 3B)
FUZZY_THRESHOLD=80
OFF_CACHE_TTL_DAYS=30
```

---

## Testing

- [ ] OCR with sample receipt images
- [ ] Parser tests per store chain
- [ ] Matching tests (exact, fuzzy, miss)
- [ ] GS1 parsing tests
- [ ] Integration test: image → inventory
