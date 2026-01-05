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
- [ ] Seed data: categories with default expiry days

### Backend API
- [x] FastAPI project structure — ✅ Complete with routing, config, logging
- [ ] Inventory CRUD + consume endpoint
- [ ] Products CRUD + barcode lookup
- [ ] Receipt upload + status endpoints
- [ ] WebSocket for real-time updates
- [x] Health check — ✅ Implemented with tests

### Receipt Pipeline
- [ ] MinerU OCR integration
- [ ] Store parsers: S-Group, K-Group, Lidl (use provided receipt samples)
- [ ] Fuzzy product matching (RapidFuzz)
- [ ] Celery task for async processing

### Frontend (iPad PWA)
- [ ] Next.js 14 + PWA setup
- [ ] Main inventory view with context sorting
- [ ] Consumption buttons ([1/4] [1/2] [3/4] [Done])
- [ ] Receipt camera capture
- [ ] Receipt review/confirmation screen
- [ ] Offline support (IndexedDB cache)

---

## Phase 2: Enhanced Input & Shopping
**Goal:** More input methods, shopping list  
**Duration:** 3-4 weeks

### Hardware Barcode Scanner
- [ ] Keyboard wedge input detection (rapid keystrokes + Enter)
- [ ] Scanner mode toggle: Add / Consume / Lookup
- [ ] Visual/audio feedback on scan
- [ ] Scan history log

### Open Food Facts Integration
- [ ] Barcode → OFF API lookup
- [ ] Cache responses in product_master.off_data
- [ ] Extract: name, brand, category, image, nutrition
- [ ] Fallback to Ollama if OFF miss

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

### Sprint 2: API Development (NEXT)
1. [ ] Category seed data script
2. [ ] Product CRUD endpoints (search, create, barcode lookup)
3. [ ] Inventory CRUD endpoints (list, add, update, delete, consume)
4. [ ] Receipt upload endpoint (file storage only)
5. [ ] API tests for all endpoints

---

## Decisions Log

**MinerU over PaddleOCR** — You already have MinerU running. Use it.

**Approximate quantities** — Users won't weigh things. [1/4] [1/2] [3/4] is good enough.

**Category-based expiry** — Default to category (meat: 5d, cheese: 25d). Override only when scanned or manual.

**Phase 1 without shopping list** — Get inventory working first. Shopping list in Phase 2.

**Hardware scanner in Phase 2** — Receipt scanning is primary. Barcode scanner is enhancement.

**Price tracking deferred** — Not core to food waste problem. Parsers extract product names and quantities only. Price/cost analytics added in future version.
