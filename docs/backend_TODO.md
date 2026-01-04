# Backend — Development TODO

**Stack:** FastAPI, SQLAlchemy, Celery, Redis, PostgreSQL

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
- [ ] FastAPI app with config (pydantic-settings)
- [ ] SQLAlchemy async + Alembic
- [ ] Celery + Redis
- [ ] Dockerfile

### Models
- [ ] ProductMaster, StoreProductAlias
- [ ] InventoryItem, ConsumptionLog
- [ ] Receipt
- [ ] Category (seed data)

### API Endpoints

**Inventory**
- [ ] `GET /api/inventory` — list with filters (context, category, expiring)
- [ ] `POST /api/inventory` — add item
- [ ] `PATCH /api/inventory/{id}` — update quantity/status
- [ ] `DELETE /api/inventory/{id}` — remove
- [ ] `POST /api/inventory/{id}/consume` — log consumption
- [ ] `POST /api/inventory/reconcile` — batch sync recovery

**Products**
- [ ] `GET /api/products` — search (fuzzy)
- [ ] `POST /api/products` — create
- [ ] `GET /api/products/barcode/{bc}` — lookup

**Receipts**
- [ ] `POST /api/receipts/scan` — upload image
- [ ] `POST /api/receipts/batch` — upload multiple (Phase 2)
- [ ] `GET /api/receipts/{id}` — status + results
- [ ] `POST /api/receipts/{id}/confirm` — confirm items

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
