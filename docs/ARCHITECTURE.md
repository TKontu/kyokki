# Kyokki — System Architecture

## 1. Vision & Design Principles

### Core Vision
Self-hosted kitchen inventory system that **reduces food waste** through intelligent automation. Track everything from fresh produce to dry goods, seasonings to coffee filters. Primary input is receipt scanning — not manual entry.

### Design Principles
- **Minimal Friction** — Receipt scan adds 10+ items. Single-tap consumption. Hardware scanner support.
- **Smart Defaults** — Category-based expiry (meat: 5 days, cheese: 25 days). Learns from corrections.
- **Context-Aware** — Shows breakfast items in morning, expiring items always on top.
- **Local-First** — All processing on homelab. Ollama for AI. MinerU for OCR. No cloud.
- **Approximate is OK** — Quantity tracking is approximate (1/4, 1/2, 3/4). Expiry is estimated unless scanned.

### What This Is NOT
- Not a recipe app (Phase 4)
- Not a meal planner (Phase 4)
- Not a nutrition tracker

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     iPad PWA (Always On)                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐  │
│  │ Receipt  │ │ Barcode  │ │Inventory │ │ Shopping │ │  Context  │  │
│  │ Scanner  │ │ Scanner  │ │   List   │ │   List   │ │ Selector  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────────┘  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTPS / WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Traefik (SSL/Routing)                           │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  FastAPI      │    │ Celery Worker │    │  WebSocket    │
│  REST API     │    │ Background    │    │  Real-time    │
│               │    │ Processing    │    │  Updates      │
└───────┬───────┘    └───────┬───────┘    └───────────────┘
        │                    │
        └──────────┬─────────┘
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Processing Layer                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │ MinerU OCR  │  │ Store       │  │ Open Food   │  │ Ollama     │  │
│  │ (Homelab)   │  │ Parsers     │  │ Facts API   │  │ (Fallback) │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL              │  Redis           │  File Storage         │
│  • Product Master        │  • Task Queue    │  • Receipt Images     │
│  • Store Aliases         │  • Cache         │  • Product Photos     │
│  • Inventory Items       │                  │                       │
│  • Consumption Log       │                  │                       │
│  • Shopping List         │                  │                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Model

### Core Tables

```sql
-- Canonical products (the "truth")
product_master (
  id UUID PK,
  canonical_name VARCHAR,          -- "Valio Whole Milk 1L"
  category VARCHAR,                -- dairy, produce, meat, frozen, pantry
  storage_type VARCHAR,            -- refrigerator, freezer, pantry
  default_shelf_life_days INT,     -- 7 (unopened)
  opened_shelf_life_days INT,      -- 4 (after opening)
  unit_type VARCHAR,               -- volume, weight, count, unit
  default_unit VARCHAR,            -- ml, g, pcs
  default_quantity DECIMAL,        -- 1000, 500, 6
  min_stock_quantity DECIMAL,      -- NULL or threshold for auto-shopping-list
  reorder_quantity DECIMAL,        -- How much to add to shopping list
  off_product_id VARCHAR,          -- Open Food Facts ID (cached)
  off_data JSONB,                  -- Cached OFF data (nutrition, image, etc.)
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- How stores name products on receipts
store_product_alias (
  id UUID PK,
  product_master_id FK,
  store_chain VARCHAR,             -- s-market, prisma, k-citymarket, lidl
  receipt_name VARCHAR,            -- "VALIO MAITO 1L"
  barcode VARCHAR,                 -- EAN-13, UPC, or GS1 GTIN
  confidence_score FLOAT,
  manually_verified BOOLEAN,
  occurrence_count INT,
  last_seen TIMESTAMP
)

-- Actual items in fridge
inventory_item (
  id UUID PK,
  product_master_id FK,
  receipt_id FK NULL,
  
  -- Quantity (approximate)
  initial_quantity DECIMAL,
  current_quantity DECIMAL,
  unit VARCHAR,
  
  -- Status
  status VARCHAR,                  -- sealed, opened, partial, empty, discarded
  purchase_date DATE,
  expiry_date DATE,                -- From GS1 scan or calculated
  expiry_source VARCHAR,           -- scanned, calculated, manual
  opened_date DATE NULL,
  
  -- Tracking
  batch_number VARCHAR NULL,       -- From GS1 DataMatrix
  location VARCHAR,                -- main_fridge, freezer, pantry
  notes TEXT,
  created_at TIMESTAMP,
  consumed_at TIMESTAMP NULL
)

-- Consumption history
consumption_log (
  id UUID PK,
  inventory_item_id FK,
  product_master_id FK,
  action VARCHAR,                  -- use_partial, use_full, discard, adjust
  quantity_consumed DECIMAL,
  consumption_context VARCHAR,     -- breakfast, lunch, dinner, snack, cooking
  logged_at TIMESTAMP
)

-- Receipt processing
receipt (
  id UUID PK,
  store_chain VARCHAR,
  purchase_date DATE,
  image_path VARCHAR,
  ocr_raw_text TEXT,
  ocr_structured JSONB,
  processing_status VARCHAR,       -- queued, processing, completed, failed
  batch_id UUID NULL,              -- For multi-receipt batch processing
  items_extracted INT,
  items_matched INT,
  created_at TIMESTAMP
)

-- Shopping list
shopping_list_item (
  id UUID PK,
  product_master_id FK NULL,       -- NULL for free-text items
  name VARCHAR,                    -- Display name
  quantity DECIMAL,
  unit VARCHAR,
  priority VARCHAR,                -- urgent, normal, low
  source VARCHAR,                  -- manual, auto_restock, recipe
  is_purchased BOOLEAN DEFAULT FALSE,
  added_at TIMESTAMP,
  purchased_at TIMESTAMP NULL
)

-- Category defaults (seed data)
category (
  id VARCHAR PK,                   -- dairy, produce, meat, etc.
  display_name VARCHAR,
  icon VARCHAR,                    -- emoji
  default_shelf_life_days INT,     -- Fallback: meat=5, cheese=25, etc.
  meal_contexts VARCHAR[],         -- ["breakfast", "cooking"]
  sort_order INT
)
```

---

## 4. Input Methods

### 4.1 Receipt Scanning (Primary)
```
Photo → MinerU OCR → Store Parser → Product Matching → Review → Inventory
```

**Multi-Receipt Batch Mode:**
- Capture multiple receipt photos
- Queue persists across app restarts
- Process all, review consolidated results
- Group by source receipt

### 4.2 Hardware Barcode Scanner
```
Scan → Detect Input Mode → Lookup/Add/Consume → Feedback
```

**Modes:**
- **Add Mode**: Scan creates/increments inventory
- **Consume Mode**: Scan decrements/removes
- **Lookup Mode**: Scan shows product info

**Detection:** Rapid keystrokes + Enter = scanner input (vs. typing)

### 4.3 GS1 DataMatrix Scanning
Extracts embedded data from 2D barcodes:
- `(01)` GTIN → Product lookup
- `(17)` Expiry date → Direct use (no estimation!)
- `(10)` Batch number → Recall tracking
- `(310x)` Weight → Actual weight for variable items

### 4.4 Camera Barcode (Fallback)
For items without receipts, use device camera.

### 4.5 Manual Entry
Last resort. Keep minimal.

---

## 5. External Integrations

### 5.1 MinerU OCR (Homelab)
Your existing MinerU instance for receipt text extraction.
- Endpoint: configurable
- Supports Finnish/Swedish/English

### 5.2 Open Food Facts
Free product database for enrichment.
```
GET https://world.openfoodfacts.org/api/v2/product/{barcode}
```

**Data Retrieved:**
- Product name (localized)
- Brand
- Category → map to system categories
- Product image
- Nutrition info, Nutri-Score
- Ingredients

**Caching:** Store in `product_master.off_data` to reduce API calls.

### 5.3 Ollama (Fallback)
For unknown products when OCR + fuzzy match + OFF all fail.
- Product identification from receipt text
- Category inference

---

## 6. Smart Features

### 6.1 Context-Aware Sorting
```python
def sort_inventory(items, context, time):
    # Priority: Expiring → Context-relevant → Frequently used
    return sorted(items, key=lambda i: (
        expiry_urgency(i),      # 0=expired, 1=today, 2=tomorrow...
        context_relevance(i),   # 0=matches context, 10=doesn't
        usage_frequency(i)      # Lower = more used
    ))
```

**Contexts:** breakfast, lunch, dinner, snack, cooking

### 6.2 Approximate Quantity Tracking
Users won't weigh things. Offer simple options:
- **Proportional:** [1/4] [1/2] [3/4] [Done]
- **Count:** [-1] [-2] [-3] [Custom]

### 6.3 Approximate Expiry
Unless scanned from GS1 DataMatrix:
```python
CATEGORY_DEFAULTS = {
    'meat': 5,
    'dairy': 7,
    'milk': 5,
    'cheese': 25,
    'produce': 5,
    'frozen': 90,
    'pantry': 365,
}
```

### 6.4 Minimum Stock & Auto-Shopping
- Per-product threshold: "Always have 2L milk"
- When below, auto-add to shopping list
- Mark auto-added items distinctly

### 6.5 Sync Recovery
For out-of-sync situations:
- Quick "Mark as Gone" action
- "Clear Expired" batch action
- Easy quantity adjustment
- "I just bought this" manual add

---

## 7. Shopping List

### Features
- Manual add (free text or product search)
- Auto-add from minimum stock
- Priority flags: **Urgent** | Normal | Low
- Mark purchased → optionally add to inventory
- Aggregate by store/category

### Urgent Flag
- Visual distinction (color, position)
- Urgent items always at top
- Auto-escalate when critically low

---

## 8. API Endpoints

```
# Inventory
GET    /api/inventory              List (with context, filters)
POST   /api/inventory              Add item
PATCH  /api/inventory/{id}         Update
DELETE /api/inventory/{id}         Remove
POST   /api/inventory/{id}/consume Log consumption
POST   /api/inventory/reconcile    Batch update for sync recovery

# Products
GET    /api/products               Search
POST   /api/products               Create
GET    /api/products/barcode/{bc}  Lookup by barcode
POST   /api/products/enrich/{id}   Trigger OFF lookup

# Receipts
POST   /api/receipts/scan          Upload single image
POST   /api/receipts/batch         Upload multiple images
GET    /api/receipts/{id}          Get status/results
POST   /api/receipts/{id}/confirm  Confirm items

# Shopping List
GET    /api/shopping               Get list
POST   /api/shopping               Add item
PATCH  /api/shopping/{id}          Update (priority, quantity)
DELETE /api/shopping/{id}          Remove
POST   /api/shopping/{id}/purchase Mark purchased

# Scanner
POST   /api/scanner/input          Process barcode input
GET    /api/scanner/mode           Get current mode
POST   /api/scanner/mode           Set mode (add/consume/lookup)

# WebSocket (Real-Time Updates)
WS     /api/ws                     Real-time broadcasts

# System
GET    /api/health                 Health check
```

---

## 9. WebSocket Real-Time Updates

### 9.1 Architecture
The system uses **Redis Pub/Sub** with WebSocket broadcasting for real-time updates.

```
API Endpoint → Redis Publish → Redis Listener → ConnectionManager → WebSocket Clients
```

**Flow:**
1. API endpoint makes a change (create inventory, process receipt)
2. Publishes message to Redis `updates` channel
3. Background Redis listener receives message
4. ConnectionManager broadcasts to all connected WebSocket clients
5. Clients filter messages by `type` and `entity_id`

### 9.2 Connection
Clients connect to the WebSocket endpoint:

```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  // Filter by message type
  if (message.type === 'receipt_status') {
    updateReceiptUI(message);
  } else if (message.type === 'inventory_update') {
    updateInventoryUI(message);
  }
};
```

### 9.3 Message Format
All messages follow a standardized JSON structure:

```json
{
  "type": "receipt_status" | "inventory_update",
  "timestamp": "2026-01-06T12:34:56.789Z",
  "entity_id": "uuid-of-entity",
  "data": {
    // Type-specific payload
  }
}
```

### 9.4 Receipt Status Messages
Broadcast during receipt processing pipeline:

```json
{
  "type": "receipt_status",
  "timestamp": "2026-01-06T12:34:56.789Z",
  "entity_id": "receipt-uuid",
  "data": {
    "receipt_id": "receipt-uuid",
    "status": "processing" | "completed" | "failed" | "confirmed",
    "items_extracted": 5,
    "items_matched": 3,
    "error": null | "error message"
  }
}
```

**Status Transitions:**
1. `processing` - OCR → LLM → Matching pipeline started
2. `completed` - All processing successful, items ready for review
3. `failed` - Error occurred during processing
4. `confirmed` - User confirmed items, inventory created

### 9.5 Inventory Update Messages
Broadcast for all inventory operations:

```json
{
  "type": "inventory_update",
  "timestamp": "2026-01-06T12:34:56.789Z",
  "entity_id": "inventory-item-uuid",
  "data": {
    "inventory_item_id": "inventory-item-uuid",
    "action": "created" | "updated" | "consumed" | "deleted",
    "current_quantity": "750.00",
    "status": "opened",
    "product_name": "Milk 1L"
  }
}
```

**Actions:**
- `created` - New inventory item added
- `updated` - Item properties changed (status, location, etc.)
- `consumed` - Item quantity reduced
- `deleted` - Item removed from inventory

### 9.6 Client-Side Filtering
Since all clients receive all messages, implement client-side filtering:

```javascript
// Filter by entity ID (for specific receipt/item)
if (message.entity_id === currentReceiptId) {
  updateUI(message);
}

// Filter by message type
if (message.type === 'inventory_update' && message.data.action === 'consumed') {
  showNotification(`${message.data.product_name} consumed`);
}
```

### 9.7 Error Handling
The ConnectionManager automatically:
- Removes disconnected clients
- Handles send failures gracefully
- Logs all connection events
- Prevents broadcast failures from affecting HTTP responses

**Reconnection Strategy (Client):**
```javascript
let ws;
let reconnectAttempts = 0;
const maxReconnectDelay = 30000; // 30 seconds

function connect() {
  ws = new WebSocket('ws://localhost:8000/api/ws');

  ws.onopen = () => {
    reconnectAttempts = 0;
    console.log('WebSocket connected');
  };

  ws.onclose = () => {
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
    reconnectAttempts++;
    setTimeout(connect, delay);
  };
}

connect();
```

### 9.8 Use Cases

**Receipt Processing Progress:**
```
User uploads receipt
→ "processing" message (show spinner)
→ "completed" message (show extracted items)
→ User confirms
→ "confirmed" message (show success, update inventory list)
```

**Real-Time Inventory Sync:**
```
User consumes milk on tablet
→ "consumed" message
→ iPad display updates immediately
→ Shows new quantity and status
```

**Multi-Device Updates:**
```
Family member adds item via phone
→ "created" message
→ Kitchen iPad updates inventory list
→ All devices stay in sync
```

---

## 10. Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 14, PWA, Tailwind |
| Backend | FastAPI, Python 3.11+ |
| Database | PostgreSQL 15 |
| Queue | Celery + Redis |
| Real-Time | WebSocket + Redis Pub/Sub |
| OCR | MinerU (existing homelab) |
| LLM | vLLM with Qwen3-8B (homelab) |
| Product DB | Open Food Facts API |
| AI Fallback | Ollama (Qwen2-VL) |
| Proxy | Traefik |

---

## 11. Deployment

Docker Compose with:
- `traefik` — SSL, routing
- `frontend` — Next.js
- `api` — FastAPI
- `celery-worker` — Background tasks
- `postgres` — Database
- `redis` — Queue/cache

External services:
- MinerU OCR (your homelab)
- Ollama (your homelab)

---

## Appendix: Finnish Receipt Formats

### Input Handling by File Type

| File Type | Processing | Notes |
|-----------|------------|-------|
| **PDF** | Direct text extraction (pdfplumber) | S-Group digital receipts, clean text |
| **Image (JPG/PNG)** | MinerU OCR | Physical receipts, may need preprocessing |
| **Digital screenshot** | MinerU OCR or direct text | Lidl e-kuitti |

**Note:** Price extraction is deferred to a future version. Initial parsers focus on product identification and quantity only.

### S-Group (Prisma, S-Market, Sale)
**Source:** Digital PDF from S-kaupat  
**Detection:** `S-KAUPAT`, `Prisma`, `S-market`, `Sale`, `HOK-ELANTO`

```
KEVYTMAITOJUOMA LAKTON 1,28
MANGO KEITT/KENT/OSTEEN 1,50
0,386 KG 3,89 €/KG              ← Weight item (line after = weight info)
BARISTA KAURAJUOMA 4,50
3 KPL 1,88 €/KPL                ← Multi-quantity (line after = count)
NORM. 5,64                      ← Original price (skip)
ALENNUS -1,14                   ← Discount (skip or associate)
TOIMITUSMAKSU 11,90 11,90       ← Delivery fee (skip)
```

**Parsing rules:**
- Product line: `NAME PRICE` (price at end)
- Weight line follows: `X,XXX KG Y,YY €/KG`
- Quantity line follows: `X KPL Y,YY €/KPL`
- Skip: `NORM.`, `ALENNUS`, `VÄLISUMMA`, `YHTEENSÄ`, `TOIMITUSMAKSU`

### K-Group (K-market, K-Citymarket, K-Supermarket)
**Source:** Physical receipt photo  
**Detection:** `K-market`, `K-Citymarket`, `K-Supermarket`

```
Pilsner Urquell 4,4% 0,5l tlk    3,04
Tolkkipantti 0,15                0,15    ← Deposit (skip)
  1 KPL    0,15 €/KPL                    ← Quantity detail
Mutti kuoritut tomaatit 400g     3,76
  2 KPL    1,88 €/KPL                    ← 2 items
PLUSSA-TASAERÄ 2 KPL/4,00 EUR          ← Bundle deal header
Pirkka juustor 150g emment-moz   4,30   ← Bundle item
  2 KPL    2,15 €/KPL
PLUSSA-ETU                       0,30-  ← Discount (skip)
```

**Parsing rules:**
- Product line: `Name Price` (mixed case)
- Quantity line indented: `X KPL Y,YY €/KPL`
- Skip: `Tolkkipantti`, `PLUSSA-ETU`, `PLUSSA-TASAERÄ`, `YHTEENSÄ`, `KANTA-ASIAKAS`
- Watch for: Price can have `-` suffix for negative (discounts)

### Lidl
**Source:** Digital e-kuitti (screenshot or PDF)  
**Detection:** `Lidl`, `lidl.fi`

```
Grillimaisteri bratwurst         3,29 B
Lidl Plus -säästösi             -0,37     ← Discount (associate with previous)
Tosco.Bonus.ital.makk.c          4,99 B
Lidl Plus -säästösi             -0,57
Sandels 4,7% 24-pack            28,32 A
Päärynä                          1,48 B
0,436 kg x 3,39 EUR/kg                    ← Weight info SAME LINE pattern
Eridanous halloumi               5,78 B
  2 x 2,89    EUR                         ← Multi-quantity NEXT LINE
Baresa vihr.täyt.oliiv.p         1,32 B
  2 x 0,66    EUR
```

**Parsing rules:**
- Product line: `Name Price VATCode` (A/B/C suffix)
- Discount line: `Lidl Plus -säästösi -X,XX` → associate with previous product
- Weight inline: `X,XXX kg x Y,YY EUR/kg` after product name
- Quantity next line: `X x Y,YY EUR`
- Skip: `YHTEENSÄ`, `Korttimaksu`, `Säästöt`, `ALV%`

### Common Skip Patterns (All Stores)
```python
SKIP_PATTERNS = [
    r'^YHTEENSÄ',           # Total
    r'^VÄLISUMMA',          # Subtotal
    r'^ALV',                # VAT lines
    r'^VEROTON',            # Tax-free
    r'Tolkkipantti',        # Deposit
    r'pantti',              # Deposit
    r'^NORM\.',             # Original price
    r'^ALENNUS',            # Discount
    r'PLUSSA-ETU',          # K-group discount
    r'KANTA-ASIAKAS',       # Loyalty
    r'BONUSTA',             # Bonus
    r'Kortti:',             # Card info
    r'Viite:',              # Reference
    r'TOIMITUSMAKSU',       # Delivery
    r'säästösi',            # Lidl savings (handle specially)
]
```

### Preprocessing Requirements
- **PDF:** Use pdfplumber for text extraction (no OCR needed)
- **Images:** 
  - Deskew if rotated
  - Contrast enhancement for thermal receipts
  - MinerU OCR
- **Quality check:** If OCR confidence < 70%, flag for manual review
