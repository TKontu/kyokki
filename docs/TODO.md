# Kyokki — Development TODO

## Phase 1: MVP
**Goal:** Receipt scanning → inventory tracking → consumption logging  
**Duration:** 4-6 weeks

### Infrastructure
- [ ] Docker Compose (traefik, api, frontend, postgres, redis, celery)
- [ ] Traefik SSL config
- [ ] MinerU OCR connectivity test
- [ ] Basic CI (lint, type check)

### Database
- [x] PostgreSQL schema (see ARCHITECTURE.md) — ✅ All 7 models complete
- [x] Alembic migrations — ✅ Initial migration applied (c943e915cf61)
- [x] Seed data: categories with default expiry days — ✅ 12 categories seeded

### Backend API
- [x] FastAPI project structure — ✅ Complete with routing, config, logging
- [x] Inventory CRUD + consume endpoint — ✅ 6 endpoints, 21 tests (PR #4)
- [x] Products CRUD + barcode lookup — ✅ 6 endpoints, 15 tests (PR #3)
- [x] Receipt upload + status endpoints — ✅ 3 endpoints, 14 tests (PR #5)
- [x] WebSocket for real-time updates — ✅ /api/ws endpoint with Redis pub/sub (Sprint 3B+)
- [x] Health check — ✅ Implemented with tests

### Receipt Pipeline
- [x] MinerU OCR integration — ✅ pdfplumber + MinerU API (Sprint 3A)
- [x] Language-agnostic LLM extraction — ✅ vLLM with structured output (Sprint 3A)
- [x] Fuzzy product matching (RapidFuzz) — ✅ WRatio scorer with confidence levels (Sprint 3B)
- [ ] Celery task for async processing — Optional enhancement (currently synchronous)
- [x] WebSocket status broadcasts — ✅ Receipt & inventory updates (Sprint 3B+)

### Frontend (iPad PWA)
- [x] Next.js 14 setup (App Router, TypeScript, Tailwind, Jest/RTL)
- [x] Core UI components (Button, Card, Badge, Skeleton)
- [x] Inventory API client + useInventory hook
- [x] ExpiryBadge, QuantityBar, InventoryItemCard components
- [ ] InventoryList + Main page integration (Increments 1.6–1.7, in progress)
- [ ] Consumption flow (Phase 2 frontend)
- [ ] Receipt camera capture
- [ ] PWA / offline support

---

## Phase 2: Enhanced Input & Shopping
**Goal:** More input methods, shopping list  
**Duration:** 3-4 weeks

### Barcode Scanner API ✅ (PR #16, #20, #21)
- [x] OFF barcode lookup with product auto-create
- [x] Scanner API: `POST /api/scanner/scan` (add/consume/lookup modes)
- [x] Per-station and global mode management (Redis)
- [x] OFF unit/quantity parsing, duplicate guard, CORS config
- [ ] iPad PWA camera scanning frontend (QuaggaJS/ZXing)
- [ ] Raspberry Pi USB scanner station (Python service + evdev)

### GS1 DataMatrix Parser
- [ ] Parse AIs: expiry (AI 17), batch (AI 10), weight (AI 310x)
- [ ] Integration with scanner API for accurate expiry dates

### GS1 DataMatrix Scanning
- [ ] Parse GS1 Application Identifiers
- [ ] Extract expiry date (AI 17), batch (AI 10), weight (AI 310x)
- [ ] Use scanned expiry directly (no estimation)

### Multi-Receipt Batch Processing
- [ ] Queue multiple receipt images before processing
- [ ] Persist queue across app restarts
- [ ] Consolidated review screen
- [ ] Per-receipt metadata (store, date)

### Shopping List
- [ ] Shopping list table + API endpoints
- [ ] Manual add (product search or free text)
- [ ] Priority flags: Urgent / Normal / Low
- [ ] Mark purchased → optionally add to inventory
- [ ] Urgent items always at top

### Home Assistant Integration (REST API)
- [ ] `GET /api/ha/status` — aggregated stats for HA sensors
- [ ] `GET /api/ha/expiring` — list expiring items
- [ ] `POST /api/ha/consume` — consume by name (voice assistant)
- [ ] Documentation with HA config examples
- [ ] See: [HOME_ASSISTANT_SPEC.md](./HOME_ASSISTANT_SPEC.md), [home_assistant_TODO.md](./home_assistant_TODO.md)

---

## Phase 3: Intelligence
**Goal:** Auto-replenishment, sync recovery, analytics  
**Duration:** 3-4 weeks

### Minimum Stock & Auto-Shopping
- [ ] Per-product min_stock_quantity threshold
- [ ] Check stock after consumption events
- [ ] Auto-add to shopping list when below threshold
- [ ] Distinct visual for auto-added items

### Sync Recovery
- [ ] "Mark as Gone" swipe action
- [ ] "Clear All Expired" batch action
- [ ] Quick quantity adjustment UI
- [ ] "Just Bought" manual add flow

### Consumption Learning
- [ ] Track consumption patterns by product + context
- [ ] Suggest frequently-used items
- [ ] Predict when products will run out

### Analytics
- [ ] Consumption trends
- [ ] Waste tracking (discarded items)
- [ ] Expiry compliance rate

---

## Phase 4: Future
- [ ] Home Assistant HACS integration (native HA custom component)
- [ ] Recipe integration
- [ ] Meal planning
- [ ] Multi-user support
- [ ] Home Assistant integration
- [ ] Voice input

---

## Current Sprint

### ✅ Sprint 1: Infrastructure + Database (COMPLETE)
1. [x] Docker Compose with all services — ✅ Backend, Postgres, Redis, Celery
2. [x] PostgreSQL schema + migrations — ✅ All 7 models + Alembic
3. [x] FastAPI health endpoint — ✅ With tests
4. [ ] MinerU OCR test call
5. [ ] Traefik routing

**Merged**: PR #2 (efe2582) - 44 files, +2,125 lines

### ✅ Sprint 2: API Development (COMPLETE)
1. [x] Category seed data script — ✅ 12 categories with shelf life defaults
2. [x] Product CRUD endpoints (search, create, barcode lookup) — ✅ PR #3
3. [x] Inventory CRUD endpoints (list, add, update, delete, consume) — ✅ PR #4
4. [x] Receipt upload endpoint (file storage only) — ✅ PR #5
5. [x] API tests for all endpoints — ✅ 69 API tests passing

**Merged**:
- PR #3 (dc10fe6) - Category + Product APIs
- PR #4 (d302695) - Inventory API
- PR #5 (1e0d564) - Receipt API

**Stats**: 89 tests passing, 1,244+ lines added across Sprint 2

### ✅ Sprint 3A: OCR & LLM Extraction (COMPLETE)
1. [x] MinerU OCR integration — ✅ pdfplumber + MinerU API
2. [x] vLLM language-agnostic extraction — ✅ Replaces hardcoded store parsers
3. [x] Pydantic models for structured data — ✅ ParsedProduct, StoreInfo, ReceiptExtraction
4. [x] Comprehensive testing — ✅ 27 tests (multi-language support)
5. [x] Documentation — ✅ ADAPTIVE_PARSER_SPEC.md, vLLM guides

**Merged**:
- PR #6 (880eee5) - OCR and LLM extraction implementation
- PR #7 (9d79357) - Test fixes and documentation

**Stats**: 117 tests passing, 1 skipped

### ✅ Sprint 3B: Receipt Processing Integration (COMPLETE)
1. [x] Fuzzy product matching (RapidFuzz) — match extracted products to product_master
2. [x] Wire OCR + LLM extraction into Receipt API endpoint
3. [x] Add POST /api/receipts/{id}/confirm endpoint
4. [x] Receipt processing pipeline with status tracking

**Merged**: PR #9 (79d7114) - Receipt processing integration

### ✅ Sprint 3B+: WebSocket Real-Time Updates (COMPLETE)
1. [x] WebSocket endpoint at /api/ws
2. [x] ConnectionManager with error handling and auto-cleanup
3. [x] Redis pub/sub message broadcasting
4. [x] Receipt/Inventory status broadcasts with standardized JSON format

### ✅ Sprint 4: Scanner API + Frontend Foundations (COMPLETE)
1. [x] OFF integration: barcode lookup, product auto-create (PR #16)
2. [x] Shopping List API: 8 endpoints, 25 tests (PR #14)
3. [x] Universal Scanner API: scan/mode/stations endpoints (PR #20)
4. [x] Scanner pipeline bug fixes × 9 (CORS, Redis resilience, station mode, unit parsing, etc.) (PR #21)
5. [x] Frontend Phase 0: Next.js 14, types, API client, testing infra (PR #8)
6. [x] Frontend Phase 1 Increments 1.1–1.5: UI components, ExpiryBadge, QuantityBar, InventoryItemCard (PRs #15, #18, #21)

**Stats**: 93 backend non-DB tests passing, 9 frontend increments complete

---

## Decisions Log

**MinerU over PaddleOCR** — You already have MinerU running. Use it.

**Approximate quantities** — Users won't weigh things. [1/4] [1/2] [3/4] is good enough.

**Category-based expiry** — Default to category (meat: 5d, cheese: 25d). Override only when scanned or manual.

**Phase 1 without shopping list** — Get inventory working first. Shopping list in Phase 2.

**Hardware scanner in Phase 2** — Receipt scanning is primary. Barcode scanner is enhancement.

**Price tracking deferred** — Not core to food waste problem. Parsers extract product names and quantities only. Price/cost analytics added in future version.
