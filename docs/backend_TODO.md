# Backend — Development TODO

**Stack:** FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL

---

## 🎯 Current Status

**✅ Sprint 1 Complete** (Merged PR #2)
- All 7 database models implemented with SQLAlchemy
- 28 Pydantic schemas (Base, Create, Update, Response)
- Alembic migrations configured and applied
- PostgreSQL with timezone-aware datetimes
- 11 passing tests (model CRUD)
- Docker-first development workflow documented

**✅ Sprint 2 Complete** (Merged PRs #3, #4, #5)
- Category API: 5 endpoints, 16 tests, seed data with 12 categories
- Product API: 6 endpoints, 15 tests, barcode lookup & search
- Inventory API: 6 endpoints, 21 tests, smart consumption tracking
- Receipt API: 3 endpoints, 14 tests, file upload & storage
- Total: 69 API tests passing, 89 total tests passing

**✅ Sprint 3A Complete** (Merged PRs #6, #7)
- MinerU OCR integration (pdfplumber + MinerU API)
- vLLM-based language-agnostic extraction (adaptive parser approach)
- Pydantic models for structured receipt data
- 27 comprehensive tests for OCR and LLM extraction
- Documentation: ADAPTIVE_PARSER_SPEC.md, vLLM testing guides
- Total: 117 tests passing, 1 skipped

**✅ Sprint 3B Complete** (Merged PR #9)
- Fuzzy product matching with RapidFuzz
- Receipt processing pipeline integration
- Full OCR → LLM → Matching workflow

**✅ Sprint 3B+ Complete** (WebSocket Real-Time Updates)
- WebSocket endpoint at /api/ws
- Receipt status broadcasts (processing/completed/failed/confirmed)
- Inventory update broadcasts (created/updated/consumed/deleted)
- Redis pub/sub integration
- Comprehensive tests

**✅ PR #20 + #21 Complete** (Universal Scanner API + 9 bug fixes)
- Scanner API: `POST /api/scanner/scan`, mode management, station tracking
- OFF unit parsing, UNIQUE constraint on off_product_id, CORS env config, Redis resilience

**📍 Next: Phase 2 Remaining**
- GS1 DataMatrix parser
- Home Assistant integration
- Celery async receipt processing (optional)

---

## Directory Structure

```
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── routes/
│   │   │   ├── inventory.py
│   │   │   ├── products.py
│   │   │   ├── receipts.py
│   │   │   ├── shopping.py
│   │   │   ├── scanner.py
│   │   │   └── health.py
│   │   └── deps.py
│   ├── models/
│   │   ├── product.py
│   │   ├── inventory.py
│   │   ├── receipt.py
│   │   └── shopping.py
│   ├── services/
│   │   ├── inventory_service.py
│   │   ├── receipt_service.py
│   │   ├── matching_service.py
│   │   ├── ocr_service.py        # ✅ MinerU + pdfplumber OCR
│   │   ├── llm_extractor.py      # ✅ vLLM language-agnostic extraction
│   │   ├── off_service.py        # Open Food Facts
│   │   └── gs1_parser.py         # GS1 DataMatrix
│   ├── parsers/
│   │   ├── base.py               # ✅ Pydantic models (ParsedProduct, StoreInfo)
│   │   ├── detector.py           # Store detection (adaptive parser Phase 1)
│   │   ├── template_engine.py    # Template parser (adaptive parser Phase 1)
│   │   └── learner.py            # Template learning (adaptive parser Phase 2)
│   └── tasks/
│       ├── ocr_tasks.py
│       └── stock_tasks.py
├── alembic/
├── tests/
├── Dockerfile
└── requirements.txt
```

---

## Phase 1 Tasks

### Setup
- [x] FastAPI app with config (pydantic-settings) — ✅ Complete
- [x] SQLAlchemy async + Alembic — ✅ Complete with timezone-aware datetimes
- [x] Celery + Redis — ✅ Docker Compose configured
- [x] Dockerfile — ✅ Complete

### Models
- [x] ProductMaster, StoreProductAlias — ✅ Complete with JSONB, UUID, indexes
- [x] InventoryItem, ConsumptionLog — ✅ Complete with relationships
- [x] Receipt — ✅ Complete with JSONB for OCR results
- [x] ShoppingListItem — ✅ Complete with priority tracking
- [x] Category — ✅ Model complete with ARRAY type
- [x] Category (seed data) — ✅ 12 categories with shelf life defaults

### API Endpoints

**Category** ✅
- [x] `GET /api/categories` — list all categories
- [x] `GET /api/categories/{id}` — get category by ID
- [x] `POST /api/categories` — create category
- [x] `PATCH /api/categories/{id}` — update category
- [x] `DELETE /api/categories/{id}` — delete category

**Products** ✅
- [x] `GET /api/products` — search (fuzzy)
- [x] `POST /api/products` — create
- [x] `GET /api/products/{id}` — get by ID
- [x] `GET /api/products/barcode/{bc}` — barcode lookup
- [x] `PATCH /api/products/{id}` — update
- [x] `DELETE /api/products/{id}` — delete

**Inventory** ✅
- [x] `GET /api/inventory` — list with filters (context, category, expiring)
- [x] `POST /api/inventory` — add item
- [x] `GET /api/inventory/{id}` — get by ID
- [x] `PATCH /api/inventory/{id}` — update quantity/status
- [x] `DELETE /api/inventory/{id}` — remove
- [x] `POST /api/inventory/{id}/consume` — log consumption with smart status transitions
- [ ] `POST /api/inventory/reconcile` — batch sync recovery (Phase 3)

**Receipts** ✅
- [x] `POST /api/receipts/scan` — upload image/PDF with metadata
- [x] `GET /api/receipts/{id}` — get receipt status + metadata
- [x] `GET /api/receipts` — list receipts with filtering
- [ ] `POST /api/receipts/batch` — upload multiple (Phase 2)
- [ ] `POST /api/receipts/{id}/confirm` — confirm extracted items (after OCR)

### Receipt Processing (Adaptive Parser Approach)

**✅ Phase 1: OCR Integration (Sprint 3A Complete)**
- [x] PDF detection → pdfplumber text extraction
- [x] Image detection → MinerU OCR API
- [x] Integration tests with real receipt samples

**✅ Phase 2: LLM Extraction (Sprint 3A Complete)**
- [x] vLLM integration via OpenAI-compatible API
- [x] Language-agnostic extraction prompt
- [x] Pydantic models for validation:
```python
class ParsedProduct(BaseModel):
    name: str                    # Original language
    name_en: str | None          # English translation
    quantity: float = 1.0
    weight_kg: float | None      # For weight-based items
    volume_l: float | None       # For volume-based items
    unit: str = "pcs"            # pcs, kg, l, unit
    price: float | None          # Optional price tracking

class StoreInfo(BaseModel):
    name: str | None             # Store name
    chain: str | None            # Parent chain
    country: str | None          # ISO 3166-1 alpha-2
    language: str | None         # ISO 639-1
    currency: str | None         # ISO 4217
```

**📍 Phase 3: Integration (Sprint 3B - Next)**
- [ ] Fuzzy product matching with RapidFuzz (match to product_master)
- [ ] Celery task for async processing
- [ ] WebSocket status broadcasts
- [ ] Wire into Receipt API endpoint

**🔜 Phase 4: Template Optimization (Future - see adaptive_parser_TODO.md)**
- [ ] Store detection from OCR text
- [ ] Template parser engine for known stores (fast path)
- [ ] LLM fallback for unknown stores
- [ ] Template learning from confirmed extractions
- [ ] Confidence tracking and re-learning

### WebSocket
- [x] Connection manager — ✅ Enhanced with error handling and auto-cleanup
- [x] Broadcast inventory updates — ✅ Created/updated/consumed/deleted actions
- [x] Broadcast receipt processing status — ✅ Processing/completed/failed/confirmed
- [x] Redis pub/sub integration — ✅ Single "updates" channel
- [x] Standardized JSON message format — ✅ With type, timestamp, entity_id
- [x] WebSocket endpoint /api/ws — ✅ Real-time connection management
- [x] Comprehensive tests — ✅ Connection + integration tests

---

## Phase 2 Tasks

### Open Food Facts ✅ (PR #16 - Merged)
- [x] OFF API client (httpx AsyncClient)
- [x] Barcode lookup with error handling
- [x] Response caching in product_master.off_data (JSONB)
- [x] Category mapping (12 system categories)
- [x] Smart canonical name construction (brand + product + quantity)
- [x] Automatic product creation/update from barcode
- [x] Endpoint: `POST /api/products/enrich?barcode={barcode}`
- [x] 17/17 unit tests passing

### Universal Barcode Scanner API ✅ (PR #20 + #21)
- [x] `POST /api/scanner/scan` — add/consume/lookup modes, OFF enrichment, auto-create product
- [x] `GET/POST /api/scanner/mode` — global or per-station mode via Redis
- [x] `GET /api/scanner/stations` — active station list with scan count and online status
- [x] station_id validation, Redis resilience (graceful fallback), consume capping feedback
- [x] UNIQUE constraint on `off_product_id`, IntegrityError guard for concurrent scans
- [x] CORS `ALLOWED_ORIGINS` configurable via env var
- [x] 93 non-DB tests passing

**See:** `docs/SCANNER_ARCHITECTURE.md`

### GS1 DataMatrix Parser
```python
def parse_gs1(data: str) -> dict:
    # Parse AIs: (01) GTIN, (17) expiry, (10) batch, (310x) weight
    pass
```
- [ ] AI extraction with regex patterns
- [ ] Date parsing (YYMMDD → date)
- [ ] Weight parsing (310x format)
- [ ] Integration with scanner API
- [ ] Tests for common GS1 formats

### Shopping List ✅ (PR #14 - Merged)
- [x] ShoppingListItem model
- [x] CRUD endpoints (8 total)
- [x] Priority handling (urgent/normal/low)
- [x] WebSocket broadcasts
- [x] 25 comprehensive tests

### Multi-Receipt Batch
- [ ] Batch ID grouping
- [ ] Queue management
- [ ] Consolidated results endpoint

---

## Phase 3 Tasks

### Minimum Stock
- [ ] Stock check after consumption
- [ ] Auto-add to shopping list
- [ ] Scheduled daily check (Celery beat)

### Sync Recovery
- [ ] Reconcile endpoint for batch updates
- [ ] Bulk mark-as-consumed

---

## Key Services

### MatchingService
```python
class MatchingService:
    def match(self, receipt_text: str, store: str) -> Product | None:
        # 1. Exact match on store_product_alias
        # 2. Fuzzy match (RapidFuzz, threshold 80)
        # 3. OFF lookup by barcode (if present)
        # 4. Ollama fallback (if configured)
        pass
```

### ExpiryService
```python
CATEGORY_DEFAULTS = {
    'meat': 5, 'milk': 5, 'dairy': 7,
    'cheese': 25, 'produce': 5,
    'frozen': 90, 'pantry': 365
}

def calculate_expiry(product, purchase_date, scanned_expiry=None):
    if scanned_expiry:
        return scanned_expiry  # GS1 DataMatrix
    return purchase_date + timedelta(days=CATEGORY_DEFAULTS.get(product.category, 7))
```

---

## Environment Variables

```env
POSTGRES_HOST=postgres
POSTGRES_DB=kyokki
POSTGRES_USER=fridge
POSTGRES_PASSWORD=xxx

REDIS_HOST=redis

MINERU_HOST=http://192.168.0.xxx:8000
OLLAMA_HOST=http://192.168.0.247:11434
OLLAMA_MODEL=qwen2-vl:7b

OFF_CACHE_TTL_DAYS=30
FUZZY_THRESHOLD=80
```

---

## Dependencies

```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
alembic
pydantic
pydantic-settings
celery
redis
aiofiles
httpx
rapidfuzz
python-multipart
websockets
pdfplumber          # PDF text extraction (S-Group receipts)
```
