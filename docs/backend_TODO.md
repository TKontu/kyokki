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

**📍 Next: Sprint 3 - Receipt Processing Pipeline**
- MinerU OCR integration
- Store parsers (S-Group, K-Group, Lidl)
- Fuzzy product matching with RapidFuzz
- Celery tasks for async processing

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
│   │   ├── off_service.py        # Open Food Facts
│   │   └── gs1_parser.py         # GS1 DataMatrix
│   ├── parsers/
│   │   ├── base.py
│   │   ├── sgroup.py
│   │   ├── kgroup.py
│   │   └── lidl.py
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

### Receipt Processing

**File Type Routing**
- [ ] PDF detection → pdfplumber text extraction (S-Group digital)
- [ ] Image detection → MinerU OCR (physical receipts)

**Store Parsers**
```python
@dataclass
class ParsedItem:
    raw_text: str
    product_name: str
    quantity: float = 1.0
    unit: str = "pcs"           # pcs, kg, l
    weight_kg: float | None = None
    # price: float — deferred to future version
```

**S-Group Parser** (Prisma, S-market, Sale)
- [ ] Detection: `S-KAUPAT`, `Prisma`, `S-market`, `HOK-ELANTO`
- [ ] Product line: extract product name (price ignored for now)
- [ ] Weight items: next line `X,XXX KG Y,YY €/KG` → extract weight
- [ ] Multi-quantity: next line `X KPL Y,YY €/KPL` → extract quantity
- [ ] Skip: `NORM.`, `ALENNUS`, `TOIMITUSMAKSU`, `VÄLISUMMA`

**K-Group Parser** (K-market, K-Citymarket)
- [ ] Detection: `K-market`, `K-Citymarket`, `K-Supermarket`
- [ ] Product line: extract product name (mixed case)
- [ ] Quantity: indented `X KPL` → extract quantity
- [ ] Skip: `Tolkkipantti` (deposit), `PLUSSA-ETU`

**Lidl Parser**
- [ ] Detection: `Lidl`, `lidl.fi`
- [ ] Product line: extract name (ignore VAT suffix A/B)
- [ ] Skip discount lines: `Lidl Plus -säästösi`
- [ ] Weight inline: `X,XXX kg x` → extract weight
- [ ] Multi-quantity: next line `X x` → extract quantity

**Common**
- [ ] Skip patterns: `YHTEENSÄ`, `ALV`, `pantti`, `Kortti:`
- [ ] Fuzzy matching (RapidFuzz)
- [ ] Celery task orchestration

### WebSocket
- [ ] Connection manager
- [ ] Broadcast inventory updates
- [ ] Broadcast receipt processing status

---

## Phase 2 Tasks

### Open Food Facts
- [ ] OFF API client
- [ ] Barcode lookup
- [ ] Response caching in product_master.off_data
- [ ] Category mapping (OFF → system)

### GS1 DataMatrix Parser
```python
def parse_gs1(data: str) -> dict:
    # Parse AIs: (01) GTIN, (17) expiry, (10) batch, (310x) weight
    pass
```
- [ ] AI extraction
- [ ] Date parsing (YYMMDD → date)
- [ ] Weight parsing

### Scanner Mode API
- [ ] `GET /api/scanner/mode`
- [ ] `POST /api/scanner/mode` — set add/consume/lookup
- [ ] `POST /api/scanner/input` — process barcode

### Shopping List
- [ ] ShoppingListItem model
- [ ] CRUD endpoints
- [ ] Priority handling

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
