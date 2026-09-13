# Kyokki — Development TODO

> **Priority rule (2026-09-13):** everything is ordered by distance to *MVP running on the
> kitchen iPad*. Work the Critical Path top to bottom. Items under "Deferred" are not to be
> started until the MVP is live on the device, regardless of how far along their specs are.

## 🎯 Milestone: MVP live on the iPad

### What "MVP" means here

Kyokki is valuable on the day the household stops needing anything else to answer
"what do we have, what is going off, what did we just buy". That requires exactly three
capabilities working together on the kitchen iPad, over the LAN, with no laptop involved:

| Capability | Definition | Value it delivers |
| --- | --- | --- |
| **Stock** | See what is in the fridge/freezer/pantry, sorted by urgency; add or fix an item by hand in under 10 seconds | Trust. If the list is wrong and cannot be fixed on the spot, nobody will use it. |
| **Consume** | Tap an item, tap ¼ ½ ¾ or Done, list updates instantly | Keeps stock true with near-zero effort. |
| **Receipt** | Photograph a receipt, wait, review the extracted items, fix a few, confirm; items land in stock with sensible expiry dates | The bulk-input that makes "Stock" fill itself. |

**MVP acceptance (all must hold on the iPad, from the Home Screen icon):**
1. Inventory loads in < 2 s over LAN, shows product names, expiry badges, quantity bars,
   grouped by location, urgent items first. Empty and discarded items are hidden by default.
2. Any item can be consumed (¼ ½ ¾ Done), adjusted (quantity, expiry, location), marked gone,
   or deleted. Each action reflects in the list within one second.
3. An item can be added by hand: pick an existing product or type a new name and category;
   expiry is pre-filled from category shelf life and can be overridden.
4. A receipt photo can be uploaded from the camera. Processing runs in the background; the
   app shows status and the receipt can be reopened later from a Receipts list.
5. The review screen lists each extracted item with its matched product (or "new"), quantity
   and unit. Every field is editable, items can be skipped, a different product can be picked.
6. Confirm creates inventory items for all kept rows, auto-creating products for new ones with
   a category so that expiry defaults are meaningful. The home list refreshes.
7. Five real Finnish receipts (S-Market, K-Market, Lidl, Prisma, Tokmanni or similar) go
   through the pipeline end to end from the iPad, each completing in under two minutes.
8. Backend and frontend CI are green on `main`; no secrets tracked; a written runbook takes the
   prod compose stack from zero to "iPad shows inventory".

**Explicitly outside MVP:** offline mode and service worker, HTTPS/Traefik, WebSocket live
updates (polling is the MVP answer), GS1 DataMatrix, barcode camera scanning, hardware scanner
stations, shopping list UI, minimum-stock automation, Home Assistant, batch receipts,
analytics, Mealie, multi-user.

### Increment plan

PR-sized, each with tests, each independently mergeable. IDs are stable; reference them in
branch names (`feat/mvp-c2-consumption-sheet`) and PR titles. Estimates are planning hours,
not promises. "Wave" groups increments that can run in parallel; a wave starts when the
previous wave is merged. Backend and frontend increments inside a wave are independent.

| ID | Wave | Side | Increment | Est. | Depends on |
| --- | --- | --- | --- | --- | --- |
| MVP-F1 | 1 | repo | Green CI and secrets out of git | 3h | — |
| MVP-F2 | 1 | infra | Deployable prod stack + runbook, iPad loads inventory | 5h | F1 |
| MVP-S1 | 2 | backend | `product_name` and `category` on inventory responses | 3h | F1 |
| MVP-R1 | 2 | backend | Typed extracted items with per-item match + suggested category | 6h | F1 |
| MVP-R2 | 2 | backend | Confirm creates products for new items; expiry/location overrides | 5h | R1 |
| MVP-C1 | 2 | frontend | BottomSheet and Toast primitives | 5h | — |
| MVP-C2 | 2 | frontend | ConsumptionSheet wired to consume mutation | 6h | C1 |
| MVP-S2 | 3 | frontend | Stock view: urgency sort, location groups, hide inactive, uses `product_name` | 5h | S1 |
| MVP-S3 | 3 | frontend | Quick Add item (product search or new product) | 8h | C1, S1 |
| MVP-S4 | 3 | frontend | Item edit sheet: adjust quantity/expiry/location, mark gone, delete | 5h | C1 |
| MVP-R3 | 3 | backend | Background receipt processing, status transitions, 202 response | 5h | R1 |
| MVP-R4 | 3 | pipeline | Real-receipt validation on the homelab, LLM settings that finish | 6h | F2, R1 |
| MVP-R5 | 4 | frontend | Receipt types, API module, hooks with status polling | 5h | R1, R2, R3 |
| MVP-R6 | 4 | frontend | Scan page: camera capture, upload, processing status | 6h | R5 |
| MVP-R7 | 4 | frontend | Receipt review page: edit, re-match, skip, confirm | 12h | R5, R6, C1 |
| MVP-R8 | 4 | frontend | Receipts list: reopen unconfirmed receipts | 3h | R5 |
| MVP-P1 | 5 | frontend | AppShell: navigation, persistent Scan button, landscape layout | 5h | S2, R6 |
| MVP-P2 | 5 | frontend | PWA manifest, icons, Home Screen install, polling refresh | 4h | P1 |
| MVP-P3 | 6 | all | Acceptance week on the iPad, friction log | — | everything |

Total planned: ~97h across 18 increments. Critical path through the backend receipt work
(R1 → R2 → R3 → R5 → R7) is ~33h, so frontend Stock/Consume work fills the gaps in waves 2–3.

### Increment detail

#### MVP-F1 — Green CI and secrets out of git
- [x] `git rm --cached stack.env`; `stack.env` and `local.env` ignored; `stack.env.example`
  committed; `CLAUDE.md` corrected (branch `fix/mvp-f1-green-ci-secrets`).
- [ ] Operator: rotate the exposed Postgres password and LLM key on the homelab, then purge
  `stack.env` from history with `git filter-repo` and force-push (runbook in `HANDOFF.md`).
  The repo is public, so rotation is what closes the exposure; the purge is hygiene.
- [x] `ruff` pinned to `0.12.12` in `requirements.txt` and installed from that pin in CI;
  `ruff format --check` is now a blocking step; `UP038` in `broadcast_helpers.py` fixed.
- [x] Backend CI `Test with pytest` job had failed on every run since April (never green).
  Reproduced against Docker Postgres + Redis: fixture `sample_category` collided with seeded
  categories; the app's pooled engine and cached Redis client leaked across pytest-asyncio
  event loops; `requires_ollama` tests ran in CI; `POST /api/shopping/` always 500'd because
  `logger.info(extra={"name": ...})` overwrites a reserved LogRecord field. All fixed; 247
  tests pass locally with `KYOKKI_TEST_REQUIRE_DB=1` (CI now sets it). Confirm green on the PR.
- [ ] Known debt, not in F1: `mypy backend/app/` reports 171 strict-mode errors and the CI step
  is `continue-on-error`. Track as QUAL work after MVP.
- **Acceptance:** both CI workflows green on `main`; `git ls-files | grep -E '\.env'` lists only
  `.env.example` and `stack.env.example`.

#### MVP-F2 — Deployable prod stack + runbook
- `docker-compose.prod.yml`: replace the hardcoded `NEXT_PUBLIC_API_URL=http://192.168.0.1:17300/api`
  with `${KYOKKI_HOST}`-based value read from `stack.env`; document that `ALLOWED_ORIGINS`
  must include `http://<KYOKKI_HOST>:17301`.
- `docs/DEPLOY.md`: prerequisites, `stack.env` from example, `docker compose -f
  docker-compose.prod.yml up -d --build`, `alembic upgrade head`, seed categories
  (`python -m app.db.seed_categories`), health check URL, open on iPad, add to Home Screen.
- Run it on the homelab. Add a few inventory rows via the API and confirm the iPad renders them.
- **Acceptance:** iPad Safari shows the inventory list from the prod stack; runbook followed
  verbatim by someone who did not write it.

#### MVP-S1 — `product_name` and `category` on inventory responses
- `InventoryItemResponse` gains `product_name: str` and `category: str` (from
  `ProductMaster` via the relationship; `selectinload` in `crud/inventory_item.py`). The
  consume endpoint already looks the name up for broadcasts; reuse that path.
- Frontend `types/inventory.ts` updated; `InventoryList` drops the `productNames` prop path
  once S2 lands (keep it optional until then).
- **Acceptance:** `GET /api/inventory` returns names without an extra products request;
  existing inventory tests extended.

#### MVP-R1 — Typed extracted items with per-item match and suggested category
- New schema `ExtractedItem` in `schemas/receipt.py`: `name`, `name_en`, `quantity`, `unit`,
  `price`, `product_id | None`, `match_score | None`, `match_confidence | None`,
  `suggested_category | None`. `ReceiptResponse` exposes `items: list[ExtractedItem]`
  (derived from `ocr_structured`), plus `store` and `purchase_date` if extracted.
- `ReceiptProcessingService` writes the match result *per item* (today only the count
  survives). Unmatched items keep `product_id = null`.
- LLM prompt asks for `suggested_category` constrained to the seeded category ids; invalid
  values are dropped, not failed. This is what makes auto-created products get a sane expiry.
- Frontend `types/receipt.ts` rewritten to mirror the schema (the current `ParsedProduct`
  type describes fields the backend never produced).
- **Acceptance:** tests in `tests/services/test_receipt_processing.py` assert per-item
  `product_id` and `suggested_category` round-trip through `GET /receipts/{id}`.

#### MVP-R2 — Confirm creates products for new items; overrides
- `ConfirmedItemCreate`: `product_id: UUID | None`, `name: str | None`, `category: str | None`,
  `quantity`, `unit`, `purchase_date`, `expiry_date: date | None`, `location: str = "main_fridge"`.
  Rule: `product_id` or (`name` and `category`) required.
- When `product_id` is null: create `ProductMaster` (canonical_name = name, category, shelf
  life from the category default, `unit_type`/`default_unit` derived from `unit`), then the
  inventory item. Expiry = override if given else purchase_date + product shelf life.
- Broadcast `inventory created` for each item (rule: mutating endpoints broadcast).
- **Acceptance:** confirm with a mix of matched, new, and skipped items yields the right
  product and inventory rows; duplicate confirm of the same receipt is rejected (409).

#### MVP-R3 — Background receipt processing
- `POST /receipts/{id}/process` sets `processing_status = "processing"`, schedules the
  pipeline via FastAPI `BackgroundTasks` with its own DB session, returns `202` with the
  receipt. `GET /receipts/{id}` reflects `processing → completed | failed` with `error`
  persisted on failure. Existing WebSocket broadcasts unchanged.
- Celery stays out of scope; the worker container can be removed from compose or left idle.
- **Acceptance:** endpoint returns within 200 ms in tests with the pipeline mocked; status
  transitions covered; a second `/process` while processing returns 409.

#### MVP-R4 — Real-receipt validation on the homelab
- Run at least five real receipts through the deployed stack via the API. Record per receipt:
  OCR time, LLM time, items extracted, items matched, failures. Append to
  `docs/vLLM_MANUAL_TEST.md`.
- Resolve the thinking-loop timeouts noted there: disable thinking for Qwen3 via
  `chat_template_kwargs: {enable_thinking: false}` or switch `LLM_MODEL`; cap `max_tokens`.
  Whatever works becomes the documented default in `.env.example` / `stack.env.example`.
- **Acceptance:** 5/5 receipts reach `completed` in under 120 s each with ≥ 80 % of line
  items extracted. If this cannot be met, stop and file a DEC before building R6/R7.

#### MVP-C1 — BottomSheet and Toast primitives
- `components/ui/BottomSheet.tsx`: portal, backdrop, slide-up, ESC and backdrop close, focus
  trap, 44 pt controls. `components/ui/Toast.tsx` + `hooks/useToast.ts`: success/error,
  auto-dismiss, stacking. React context; no Zustand needed for MVP.
- **Acceptance:** RTL tests for open/close, focus, dismiss; used by C2, S3, S4, R7.

#### MVP-C2 — ConsumptionSheet
- Tap an `InventoryItemCard` → BottomSheet with ¼ ½ ¾ Done. Amount = fraction of
  `initial_quantity`, capped at `current_quantity`; Done = `current_quantity`.
- Calls `useConsumeInventoryItem` (optimistic update exists), toast on success, rollback plus
  error toast on failure. Wire `onConsume` from `page.tsx` through `InventoryList`.
- **Acceptance:** calculation tests (¼ of 1000 ml = 250 ml; cap when 100 ml left), flow test
  with msw, rollback test.

#### MVP-S2 — Stock view
- Default query hides `empty` and `discarded`. Sort by `expiry_date` ascending. Group by
  `location` (Fridge / Freezer / Pantry) with counts. "Expiring soon" (≤ 3 days) pinned on top.
- Uses `product_name` from S1; remove the products list fetch from `page.tsx`.
- **Acceptance:** tests for sort, grouping, hiding; visual check in iPad landscape.

#### MVP-S3 — Quick Add item
- "+ Add" opens a BottomSheet: product search (`GET /api/products?search=`) with
  "Create new: <typed name>" fallback that asks for category (from `GET /api/categories`),
  then quantity, unit, location; expiry pre-filled from category shelf life, editable.
- New product → `POST /api/products` then `POST /api/inventory`. `lib/api/categories.ts`,
  `hooks/useCategories.ts`, `hooks/useProducts.ts` create mutation.
- **Acceptance:** add existing and add new both land in the list; validation for quantity > 0.

#### MVP-S4 — Item edit sheet
- Long-press or "⋯" on a card: adjust current quantity, change expiry date, move location,
  "Mark as gone" (`PATCH status=discarded`), "Delete" (confirmation step, then `DELETE`).
- **Acceptance:** each action has a test; list refreshes; gone items disappear from default view.

#### MVP-R5 — Receipt types, API module, hooks
- `lib/api/receipts.ts`: `scan(file, meta)` multipart upload (do not set JSON content type),
  `get`, `list`, `process`, `confirm`. `hooks/useReceipts.ts`: `useReceipt(id)` polls every
  3 s while `processing`, stops on `completed | failed | confirmed`; `useReceiptList`,
  `useUploadReceipt`, `useConfirmReceipt` (invalidates inventory lists).
- **Acceptance:** msw tests including polling stop conditions and multipart body.

#### MVP-R6 — Scan page
- `/scan`: `<input type="file" accept="image/*" capture="environment">` (works over plain
  HTTP on iOS; `getUserMedia` does not), preview thumbnail, optional store and date, Upload →
  scan → process → navigate to `/receipt/[id]`. `ProcessingStatus` shows queued/processing
  with elapsed time and a failure state with retry.
- **Acceptance:** tests for the happy path and the failure path; manual test on the iPad.

#### MVP-R7 — Receipt review page
- `/receipt/[id]`: one row per `ExtractedItem`: name (editable), quantity + unit (editable),
  matched product with confidence badge or "New product" with category picker
  (pre-filled from `suggested_category`), "Change product" search, include/skip toggle.
  Footer: n items to add, Confirm. On success: toast, invalidate inventory, go home.
- Confirmed receipts open read-only with a summary.
- **Acceptance:** tests for editing, re-matching, skipping, payload shape sent to confirm,
  and the read-only state.

#### MVP-R8 — Receipts list
- `/receipts`: recent receipts with status chip, item counts, date; tap opens review. Lets the
  user leave during processing and come back.
- **Acceptance:** list renders all statuses; completed-unconfirmed are visually flagged.

#### MVP-P1 — AppShell
- Persistent header/side rail: Inventory, Scan (primary, always visible), Receipts. Remove the
  `/components-demo` link from the header (page may stay for development). Landscape-first
  layout with a two-column inventory grid on iPad width; 44 pt targets everywhere.
- **Acceptance:** navigation tests; every MVP flow reachable within two taps from home.

#### MVP-P2 — PWA manifest and always-on refresh
- `app/manifest.ts` (Next 14 metadata route): name, icons 192/512, `display: standalone`,
  `orientation: landscape`, theme color; `apple-touch-icon` and `apple-mobile-web-app-*` meta.
- Inventory queries: `refetchInterval` 30 s, `refetchOnWindowFocus`, `staleTime` 10 s.
- Verify "Add to Home Screen" over HTTP on the iPad. If iOS refuses standalone mode without
  HTTPS, file a DEC to pull Traefik/TLS into MVP; otherwise TLS stays deferred.
- **Acceptance:** app launches from the Home Screen icon without browser chrome; list updates
  within a minute after a change made elsewhere.

#### MVP-P3 — Acceptance week
- Use it for a week. Scan every receipt, consume from the iPad, fix stock by hand when wrong.
  Log friction in this file under "Post-MVP frontier". Tick the eight acceptance items above.

### Post-MVP frontier (do not start before MVP-P3)
Ordered by expected value once MVP is live.
1. WebSocket live updates in the PWA (`services/websockets.py` already broadcasts).
2. "Opened" tracking: consuming from sealed sets `opened_date` and switches to
   `opened_shelf_life_days`.
3. GS1 DataMatrix parser (`backend/app/services/gs1_parser.py` — no stub exists yet).
4. Traefik + HTTPS, service worker, offline queue.
5. Shopping list UI (API done, PR #14), minimum-stock auto-add.
6. Home Assistant REST endpoints (`HOME_ASSISTANT_SPEC.md`).
7. Barcode scanning in the PWA camera; Raspberry Pi scanner station.
8. Multi-receipt batch, consumption learning, analytics, Mealie.

---

## Phase 1: MVP
**Goal:** Receipt scanning → inventory tracking → consumption logging  
**Duration:** 4-6 weeks

### Infrastructure
- [x] Docker Compose (api, frontend, postgres, redis, celery) — ✅ dev + `docker-compose.prod.yml`; Traefik deferred
- [ ] Traefik SSL config
- [ ] MinerU OCR connectivity test
- [x] Basic CI (lint, type check, tests) — ✅ `.github/workflows/`; backend job red on main since 2026-04-20, see MVP-F1

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
- [x] InventoryList component (Increment 1.6)
- [x] Main page integration (Increment 1.7) — ✅ PR #22
- [ ] Consumption flow — **MVP-C1, MVP-C2**
- [ ] Receipt capture, review, confirm — **MVP-R1…R8**
- [ ] PWA manifest / Home Screen — **MVP-P1, MVP-P2**; offline support deferred

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

### 🚧 Sprint 5: MVP on the iPad (IN PROGRESS, started 2026-09-13)
Scope = the MVP increment plan above, waves 1–6. Nothing from "Post-MVP frontier" enters.
- Wave 1: [ ] F1  [ ] F2
- Wave 2: [ ] S1  [ ] R1  [ ] R2  [ ] C1  [ ] C2
- Wave 3: [ ] S2  [ ] S3  [ ] S4  [ ] R3  [ ] R4
- Wave 4: [ ] R5  [ ] R6  [ ] R7  [ ] R8
- Wave 5: [ ] P1  [ ] P2
- Wave 6: [ ] P3 acceptance

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

**Stats**: 93 backend non-DB tests passing, 10 frontend increments complete (111 frontend tests)

---

## Decisions Log

**MinerU over PaddleOCR** — You already have MinerU running. Use it.

**Approximate quantities** — Users won't weigh things. [1/4] [1/2] [3/4] is good enough.

**Category-based expiry** — Default to category (meat: 5d, cheese: 25d). Override only when scanned or manual.

**Phase 1 without shopping list** — Get inventory working first. Shopping list in Phase 2.

**Hardware scanner in Phase 2** — Receipt scanning is primary. Barcode scanner is enhancement.

**Price tracking deferred** — Not core to food waste problem. Parsers extract product names and quantities only. Price/cost analytics added in future version.
