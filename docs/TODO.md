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
| MVP-R0 | 1 | pipeline | Extraction feasibility spike: text LLM vs vision model on a real receipt | 2h | — |
| MVP-S1 | 2 | backend | `product_name` and `category` on inventory responses | 3h | F1 |
| MVP-R1 | 2 | backend | Typed extracted items with per-item match + suggested category | 6h | F1 |
| MVP-R2 | 2 | backend | Confirm creates products for new items; expiry/location overrides | 5h | R1 |
| MVP-C1 | 2 | frontend | BottomSheet and Toast primitives | 5h | — |
| MVP-C2 | 2 | frontend | ConsumptionSheet wired to consume mutation | 6h | C1 |
| MVP-S2 | 3 | frontend | Stock view: urgency sort, location groups, hide inactive, uses `product_name` | 5h | S1 |
| MVP-S3 | 3 | frontend | Quick Add item (product search or new product) | 8h | C1, S1 |
| MVP-S4 | 3 | frontend | Item edit sheet: adjust quantity/expiry/location, mark gone, delete | 5h | C1 |
| MVP-R3 | 3 | backend | Background receipt processing, status transitions, 202 response | 5h | R1 |
| MVP-R3b | 3 | backend | Generic heuristic line-parser fallback when extraction fails | 3h | R1 |
| MVP-R4 | 3 | pipeline | Real-receipt validation on the homelab, LLM settings that finish | 6h | F2, R0, R1 |
| MVP-R5 | 4 | frontend | Receipt types, API module, hooks with status polling | 5h | R1, R2, R3 |
| MVP-R6 | 4 | frontend | Scan page: camera capture, upload, processing status | 6h | R5 |
| MVP-R7 | 4 | frontend | Receipt review page: edit, re-match, skip, confirm | 12h | R5, R6, C1 |
| MVP-R8 | 4 | frontend | Receipts list: reopen unconfirmed receipts | 3h | R5 |
| MVP-P1 | 5 | frontend | AppShell: navigation, persistent Scan button, landscape layout | 5h | S2, R6 |
| MVP-P2 | 5 | frontend | PWA manifest, icons, Home Screen install, polling refresh | 4h | P1 |
| MVP-P3 | 6 | all | Acceptance week on the iPad, friction log | — | everything |

Total planned: ~105h across 20 increments. Critical path through the backend receipt work
(R1 → R2 → R3 → R5 → R7) is ~35h, so frontend Stock/Consume work fills the gaps in waves 2–3.

Amended 2026-09-13 from `docs/PLAN_REVIEW_2026-09-13.md` (sections 6 and 8): R0 and R3b
added, alias learning folded into R1/R2, serialisation and unit decisions surfaced as DECs.

### Decisions needed before Wave 2

Operator-gated. An agent may lay out options but must not pick one and proceed.

| ID | Question | Blocks | Recommended | Status |
| --- | --- | --- | --- | --- |
| DEC-1 | Canonical unit vocabulary: `ml \| g \| pcs` with R1 normalising `kg→g`, `l→ml`, `unit→pcs`, or keep receipt-native units with display conversion | R1, C2, S3 | `ml \| g \| pcs` | **decided 2026-09-13**: `dl \| tsp \| tbsp \| g \| pcs`. ml, l and kg are not canonical; conversion factors for R1 still to confirm (see R1) |
| DEC-2 | Quantities on the wire: backend serialises `Decimal` as JSON number, or frontend types become `string` and parse at the API boundary (today the API sends `"750.00"` and the TS types say `number`) | S1, C2 | JSON number | **decided 2026-09-13**: JSON number, applied to every Decimal field in API schemas in MVP-S1 |
| DEC-3 | Frontend→API path: same-origin Next.js rewrite `/api/*` → `kyokki-api:8000` (no CORS, no build-time LAN IP), or keep `NEXT_PUBLIC_API_URL` + `ALLOWED_ORIGINS` | F2 | rewrite | **decided 2026-09-13**: rewrite; shipped in MVP-F2 (#26) |
| DEC-4 | If the R0 spike cannot finish a 60-line receipt: heuristic parser becomes primary with the LLM only categorising; switch model; or accept chunked multi-call extraction | R1, R4 | decide the fallback order now | open |

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
Amended 2026-09-13 with the deployment findings of `PLAN_REVIEW_2026-09-13.md` (S1, S5, S6, S10).
- [x] Same-origin API (decision: rewrite over CORS). `next.config.mjs` proxies `/api/*` to
  `API_INTERNAL_URL` (compose service name, build arg); `lib/api/client.ts` defaults to `/api`.
  No LAN IP in the frontend image, no `ALLOWED_ORIGINS` needed in production.
- [x] `docker-compose.prod.yml`: crash-looping `celery-worker` removed (`app.tasks` never
  existed); `celery_app.py` and the `celery` dependency deleted; Postgres and Redis host ports
  unpublished. Dev compose loses the worker too.
- [x] Migration drift: new revision adds `uq_product_master_off_product_id` (model had it since
  PR #21, schema did not); CI runs `alembic upgrade head && alembic check` before pytest.
  Root cause found on the way: `app/db/base.py` never imported the models, so Alembic
  autogenerate compared against an empty schema (and would have proposed dropping every
  table). Fixed with a registry test.
- [x] `docker-compose.prod.yml` read `POSTGRES_PASSWORD` via `${...}` interpolation, which
  Compose takes from the shell or `.env`, not from `stack.env`; Postgres now gets it via
  `env_file`. Smoke-tested locally with the real compose file under a separate project name.
- [x] Found by that smoke: the API container never started with a comma-separated
  `ALLOWED_ORIGINS` in `stack.env` (pydantic-settings JSON-decodes `list[str]` env values before
  the split validator runs). Field is now `Annotated[list[str], NoDecode]`, with tests in
  `tests/core/test_config.py`. This means the prod API had not been startable with CORS
  configured since PR #21.
- [x] Also found by the smoke (review finding C3): with one item in stock the page crashed
  with `toFixed is not a function` because Decimal quantities arrive as JSON strings.
  `lib/api/inventory.ts` now coerces `initial_quantity`/`current_quantity` to numbers at the
  API boundary (with tests). The number-vs-string wire decision (DEC 2) stays open for S1.
- [x] `python -m app.db.seed_categories` entry point for the runbook (with test).
- [x] `docs/DEPLOY.md` runbook; README Quick Start and ARCHITECTURE.md "as built" note updated.
- [ ] **Operator:** deploy on the homelab following `docs/DEPLOY.md` verbatim (rebuild the
  frontend image; `ALLOWED_ORIGINS` can go from `stack.env`), open `http://<host>:17301` on the
  iPad, confirm the inventory list renders. That ticks F2.
- **Acceptance:** iPad Safari shows the inventory list from the prod stack; runbook followed
  verbatim by someone who did not write it.

#### MVP-R0 — Extraction feasibility spike (Wave 1, time-boxed 2 h)
- Paper receipts are the common case, so OCR + extraction is on the critical path for most
  input. Prove it before Wave 2 instead of in R4. Needs only the homelab endpoints and the
  60-line S-kaupat text in `docs/vLLM_MANUAL_TEST.md`; no code merge required.
- Candidate A, text LLM after OCR (current design): `chat_template_kwargs:
  {"enable_thinking": false}` (or `/no_think`), `max_tokens` 4096, prompt trimmed to the
  fields the MVP reads (`name`, `quantity`, `unit`, `weight_kg`, `volume_l`), skip-pattern
  pre-filter on OCR lines (`YHTEENSÄ`, `ALV`, `Kortti:`, `Viite:`, `TOIMITUSMAKSU`, `NORM.`,
  `ALENNUS`, VAT table), then retry `response_format` json_schema with thinking off. If still
  failing, chunk product lines in batches of ~15 and merge.
- Candidate B, vision model straight from the image (Qwen2.5-VL class via the same
  OpenAI-compatible endpoint): one step, sees layout, no OCR language setting.
- Both are store-agnostic. The winner becomes the primary path; the other stays wired as
  a fallback. Record timings and the working `curl` in `docs/vLLM_MANUAL_TEST.md`.
- **Acceptance:** one candidate completes the 60-line receipt in under 60 s with ≥ 80 % of
  product lines. Otherwise file DEC-4's ruling before Wave 2 starts.

#### MVP-S1 — `product_name` and `category` on inventory responses
- `InventoryItemResponse` gains `product_name: str` and `category: str` (from
  `ProductMaster` via the relationship; `selectinload` in `crud/inventory_item.py`). The
  consume endpoint already looks the name up for broadcasts; reuse that path.
- Also expose `category_icon` so S2 needs no products or categories fetch at all.
- Quantities per DEC-2. Recommended: `field_serializer` emitting `float` for
  `initial_quantity`, `current_quantity` (and `ProductMasterResponse.default_quantity`), with a
  test asserting the JSON type. Today pydantic emits `"750.00"` and the TS types say `number`.
  Since F2 the frontend already coerces both quantities to numbers at the API boundary
  (`lib/api/inventory.ts`), so DEC-2 only settles the wire format; the UI no longer depends on it.
- Server-side default filter: `GET /api/inventory` hides `empty` and `discarded` unless
  `include_inactive=true`. Keeps the 30 s polling payload small on an always-on device.
- Write a `consumption_log` row on consume and on discard (`crud/inventory_item.py` writes
  none today), so P3's acceptance week produces waste and usage history.
- Frontend `types/inventory.ts` updated; `InventoryList` drops the `productNames` prop path
  once S2 lands (keep it optional until then).
- **Acceptance:** `GET /api/inventory` returns names without an extra products request;
  inactive items hidden by default; quantity JSON type asserted; existing inventory tests extended.
- As built (branch `feat/mvp-s1-inventory-product-fields`):
  - [x] Response gains `product_name`, `category`, `category_icon` and also `category_name`
    (display text for the card subtitle, so S2 needs no categories fetch). Every create,
    update, consume and get path eager-loads product and category.
  - [x] DEC-2 via one shared `JsonDecimal` type in `schemas/types.py`, applied to inventory,
    product, shopping list and consumption log schemas. Scanner responses and WebSocket
    payloads still send quantities as strings; they build their own dicts. Follow-up debt.
  - [x] `include_inactive` query parameter. An explicit `status` filter always wins.
  - [x] `consumption_log` rows: `use_partial` / `use_full` on consume (API and scanner),
    `discard` once on the transition to `discarded`, staged in the same transaction.
  - [x] Frontend types mirror the new fields; `InventoryList` prefers `item.product_name` and
    shows the category name. The `productNames` prop and products fetch go in S2.

#### MVP-R1 — Typed extracted items with per-item match and suggested category
- New schema `ExtractedItem` in `schemas/receipt.py`: `name`, `name_en`, `quantity`, `unit`,
  `price`, `product_id | None`, `match_score | None`, `match_confidence | None`,
  `suggested_category | None`. `ReceiptResponse` exposes `items: list[ExtractedItem]`
  (derived from `ocr_structured`), plus `store` and `purchase_date` if extracted.
- `ReceiptProcessingService` writes the match result *per item* (today only the count
  survives). Unmatched items keep `product_id = null`.
- Alias-first matching (the general learning mechanism): before RapidFuzz, look up
  `store_product_alias` by normalised `receipt_name` (scoped to `store_chain` when known);
  a hit is `exact`. Alias names also join the fuzzy candidate set so OCR-noise variants of a
  known line still land on the right product. The table and model exist and are unused today.
- DEC-1 ruling is `dl | tsp | tbsp | g | pcs`, so the examples below are out of date. Before
  R1 starts, confirm with the operator: `l→dl×10`, `ml→dl÷100`, `kg→g×1000`, `unit→pcs`,
  and whether tsp/tbsp ever come from receipts or only from manual entry.
- Unit normalisation per DEC-1 in one backend function with tests (`kg→g×1000`,
  `l→ml×1000`, `unit→pcs`). `ExtractedItem.unit` and `ConfirmedItemCreate.unit` use it.
- One `ReceiptStatus` enum in `schemas/receipt.py`: `uploaded | processing | completed |
  failed | confirmed`; model default and `crud/receipt.py` use it (today three values disagree).
- Category suggestion as a separate small LLM call (names in, category ids out,
  schema-constrained enum) rather than inside the main extraction prompt; invalid values are
  dropped, not failed. Only unmatched items need it. This is what makes auto-created products
  get a sane expiry.
- `ExtractedItem` also carries pre-filled `location` and the product `storage_type` derived
  from the category (`frozen→freezer`; `pantry`, `condiments`, `snacks`, `beverages→pantry`;
  else `main_fridge` / `refrigerator`), so R7 shows it and the user can change it.
- Drop the deprecated flat fields from `ReceiptExtraction`; prompt trimmed per R0's result.
- `MINERU_LANG` setting (default `fi`, today hardcoded `en`) and a real `MINERU_TIMEOUT`
  default (120 s, today `None`); send the file's actual content type.
- Frontend `types/receipt.ts` rewritten to mirror the schema (the current `ParsedProduct`
  type describes fields the backend never produced).
- **Acceptance:** tests in `tests/services/test_receipt_processing.py` assert per-item
  `product_id` and `suggested_category` round-trip through `GET /receipts/{id}`; an alias
  hit wins over a fuzzy candidate; unit normalisation and the status enum are covered.

#### MVP-R2 — Confirm creates products for new items; overrides
- `ConfirmedItemCreate`: `product_id: UUID | None`, `name: str | None`, `category: str | None`,
  `quantity`, `unit`, `purchase_date`, `expiry_date: date | None`, `location: str = "main_fridge"`.
  Rule: `product_id` or (`name` and `category`) required.
- When `product_id` is null: create `ProductMaster` (canonical_name = name, category, shelf
  life from the category default, `unit_type`/`default_unit` derived from `unit`,
  `storage_type` from the category mapping in R1), then the inventory item. Expiry =
  override if given else purchase_date + product shelf life. `location` = override if given
  else the category-derived default (never a blanket `main_fridge`).
- Learning: for every confirmed item upsert a `store_product_alias` row (`receipt_name` =
  extracted name, `store_chain` = receipt chain or `unknown`, `product_master_id`,
  `manually_verified = true`, `occurrence_count += 1`). This is what makes the second receipt
  from a store arrive mostly pre-matched.
- Broadcast `inventory created` for each item (rule: mutating endpoints broadcast).
- **Acceptance:** confirm with a mix of matched, new, and skipped items yields the right
  product, inventory and alias rows with category-derived locations; duplicate confirm of
  the same receipt is rejected (409).

#### MVP-R3 — Background receipt processing
- `POST /receipts/{id}/process` sets `processing_status = "processing"`, schedules the
  pipeline via FastAPI `BackgroundTasks` with its own DB session, returns `202` with the
  receipt. `GET /receipts/{id}` reflects `processing → completed | failed` with `error`
  persisted on failure. Existing WebSocket broadcasts unchanged.
- Migration adds `error` and `processing_started_at` to `receipt`.
- Stale-state recovery: a receipt `processing` for more than 10 minutes is treated as
  `failed` on read and on `/process` (a container restart or a hung OCR call must not leave it
  stuck behind the 409). `/process` is allowed on `failed`.
- Celery is removed in F2; nothing here depends on it.
- **Acceptance:** endpoint returns within 200 ms in tests with the pipeline mocked; status
  transitions and stale recovery covered; a second `/process` while processing returns 409;
  `/process` on a `failed` receipt re-runs.

#### MVP-R3b — Generic heuristic fallback
- When extraction fails or times out, a deterministic, store-agnostic line parser turns
  `NAME … PRICE` lines (with an optional following `n KPL` / `x,xxx KG` line) into
  `ExtractedItem` rows, so `completed` always has rows on the review screen. Marks the receipt
  `extraction_method = "heuristic"` so R7 can show a hint. The grammar in the
  `ARCHITECTURE.md` appendix is the reference; chain-specific rules stay post-MVP.
- **Acceptance:** the 60-line S-kaupat text yields ≥ 80 % of product lines with no LLM
  call; a failing LLM call degrades to heuristic rows rather than `failed`.

#### MVP-R4 — Real-receipt validation on the homelab
- Run at least five real receipts through the deployed stack via the API. Record per receipt:
  OCR time, LLM time, items extracted, items matched, failures. Append to
  `docs/vLLM_MANUAL_TEST.md`.
- Apply R0's winning settings in `llm_extractor.py`. Whatever works becomes the single
  documented default in `config.py`, `.env.example` and `stack.env.example` (today `.env.example`
  says `Qwen3-4B-Instruct` while `config.py` and `stack.env.example` say `qwen3-8B`). Include OCR language as a measured variable.
- **Acceptance:** 5/5 receipts reach `completed` in under 120 s each with ≥ 80 % of line
  items extracted. If this cannot be met, stop and file a DEC before building R6/R7.

#### MVP-C1 — BottomSheet and Toast primitives
- `components/ui/BottomSheet.tsx`: portal, backdrop, slide-up, ESC and backdrop close, focus
  trap, 44 pt controls. `components/ui/Toast.tsx` + `hooks/useToast.ts`: success/error,
  auto-dismiss, stacking. React context; no Zustand needed for MVP.
- **Acceptance:** RTL tests for open/close, focus, dismiss; used by C2, S3, S4, R7.
- As built (branch `feat/mvp-c1-bottomsheet-toast`):
  - [x] `BottomSheet`: portal, `role="dialog"` named by its title, ESC / backdrop / close
    button, Tab wrap, focus restored to the trigger, body scroll lock, optional footer,
    safe-area bottom padding. Slide-up is a CSS keyframe (`animate-sheet-up`), not a
    frame-driven transition: a hidden tab or resuming PWA pauses `requestAnimationFrame`, and
    the first version left the sheet stuck off-screen in that case (found in the browser check).
  - [x] `ToastProvider` + `useToast()`: `success` / `error` with an optional action (e.g. a
    future Undo), 3 s / 5 s auto-dismiss, at most 3 stacked, top centre above sheets. Mounted in
    `app/providers.tsx` inside the query client, so any component or hook can raise toasts.
  - [x] Demo sections in `/components-demo`. Dropped for MVP: sheet sizes, warning/info toasts.

#### MVP-C2 — ConsumptionSheet
- Tap an `InventoryItemCard` → BottomSheet with ¼ ½ ¾ Done. Amount = fraction of
  `initial_quantity`, capped at `current_quantity`; Done = `current_quantity`.
- Calls `useConsumeInventoryItem` (optimistic update exists), toast on success, rollback plus
  error toast on failure. Wire `onConsume` from `page.tsx` through `InventoryList`.
- **Acceptance:** calculation tests (¼ of 1000 ml = 250 ml; cap when 100 ml left), flow test
  with msw, rollback test.
- As built (branch `feat/mvp-c2-consumption-sheet`), with operator rulings of 2026-09-13:
  - [x] `components/inventory/ConsumptionSheet.tsx` opened from the card's Consume button (the
    card has no whole-card tap: `Card` renders a `<button>` and would nest the action buttons).
    ¼ ½ ¾ Done for measured units; **−1 −2 −3 Done for `pcs`/`unit`** (ruling), counts not less
    than what is left disabled. Rules and rounding live in `lib/consumption.ts`.
  - [x] **No Undo** (ruling): the backend has no clean reversal. Mistakes are fixed in S4.
  - [x] `useConsumeInventoryItem` now updates every cached inventory list optimistically (it
    only touched the detail cache, which the home page never reads), rolls all of them back on
    error, invalidates on settle, and **never retries**: `app/providers.tsx` retries mutations
    once, consuming is not idempotent, and TanStack pauses retries in a hidden tab, which left
    the optimistic value up with no error (found in the browser check against the real API).
  - [x] `lib/api/client.ts` reads FastAPI's `detail` (string or validation list) for
    `APIError.message`. The sheet shows 4xx messages as-is and "Could not update <name>" for
    5xx and network errors.
  - [x] msw is set up for Jest: `jest.polyfills.js`, `customExportConditions: ['']`, an ESM
    transform exception for `until-async`, and `test/msw/server.ts` (opt-in per test file).
    `app/__tests__/consume-flow.test.tsx` covers the optimistic update, the POST body, the
    toast and the rollback.
  - Note for S2: items with equal expiry dates come back in varying order, so cards can swap
    places after each refetch. S2's sort should add a stable tie-breaker.

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
- Status union copied from the single backend `ReceiptStatus` enum; quantity types follow DEC-2.
- **Acceptance:** msw tests including polling stop conditions and multipart body.

#### MVP-R6 — Scan page
- `/scan`: `<input type="file" accept="image/*" capture="environment">` (works over plain
  HTTP on iOS; `getUserMedia` does not), preview thumbnail, optional store and date, Upload →
  scan → process → navigate to `/receipt/[id]`. `ProcessingStatus` shows queued/processing
  with elapsed time and a failure state with retry.
- Second button "Choose a file" (`accept="image/*,application/pdf"`, no `capture`) so a
  digital e-receipt PDF saved to the iPad Files app can be uploaded; the backend already
  routes PDFs to pdfplumber, so this is the whole digital-receipt path for MVP.
- Client-side downscale before upload (canvas, long edge ≤ 2000 px, JPEG q 0.85); a 12 MP
  camera capture is 3–5 MB and inflates OCR time and prompt length.
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
  within a minute after a change made elsewhere; the runbook states the iPad setting that
  keeps the screen on (Auto-Lock: Never, or Guided Access), since a home-screen web app
  cannot do that itself.

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
9. Learned store templates (`ADAPTIVE_PARSER_SPEC.md`): chain-specific parse rules that
   skip the LLM for known formats. Generalising accelerator, not a core dependency.
10. Digital receipt import adapters: loyalty-app exports, e-receipt e-mail ingestion, PDF
    watch folder. MVP covers PDF upload via the file picker (R6).
11. Runtime simplification for single-node installs: one uvicorn worker with in-process
    broadcast, Redis optional (scanner mode state moves to Postgres).
12. Undo for consume: a backend endpoint that reverses a consume (quantity, status,
    `opened_date`) and removes its `consumption_log` row, then an Undo action on C2's toast.

---

## Phase 1: MVP
**Goal:** Receipt scanning → inventory tracking → consumption logging  
**Duration:** 4-6 weeks

### Infrastructure
- [x] Docker Compose (api, frontend, postgres, redis) — ✅ dev + `docker-compose.prod.yml`; Celery removed in MVP-F2; Traefik deferred
- [ ] Traefik SSL config
- [ ] MinerU OCR connectivity test
- [x] Basic CI (lint, type check, tests) — ✅ `.github/workflows/`; backend job green since PR #24 (MVP-F1)

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
- [ ] Background processing — FastAPI `BackgroundTasks` in **MVP-R3**; Celery removed in **MVP-F2**
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
- Wave 1: [x] F1 (PR #24; operator rotation + history purge still open)  [x] F2 (PR #26; homelab verification pending)  [ ] R0
- Decisions: [x] DEC-1 (`dl|tsp|tbsp|g|pcs`)  [x] DEC-2 (JSON number)  [x] DEC-3 (same-origin rewrite, shipped in F2)  [ ] DEC-4 (if R0 fails)
- Wave 2: [x] S1 (PR #27)  [ ] R1  [ ] R2  [x] C1 (PR #28)  [ ] C2 (PR open)
- Wave 3: [ ] S2  [ ] S3  [ ] S4  [ ] R3  [ ] R3b  [ ] R4
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
