# Kyokki — Development TODO

> **Priority rule (2026-09-13):** everything is ordered by distance to *MVP running on the
> kitchen iPad*. Work the Critical Path top to bottom. Items under "Deferred" are not to be
> started until the MVP is live on the device, regardless of how far along their specs are.
>
> **Amendment (2026-09-17):** the reviews under `docs/reviews/` added a hardening track after
> MVP-P3 in this file. Its wave H0 is MVP work and runs before the acceptance week; wave H1
> repairs MVP-R1b/R2 matching behaviour; H2 to H4 follow MVP-P3 and precede the agent track.

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
4. A receipt (e-receipt PDF, loyalty-app receipt or screenshot, or a photo of a paper receipt)
   can be shared from the phone to the Kyokki Telegram bot, or uploaded from the iPad.
   Processing runs in the background; the bot replies when it is done, and the receipt can be
   reopened later from the iPad Receipts list.
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
analytics, Mealie, multi-user, agent interface (CLI, skill, recipes; `docs/agent_TODO.md`).

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
| MVP-R1a | 2 | backend | Extraction layer: R0 request on muse-glimmer, vision fallback, inline category | 4h | F1, R0 |
| MVP-R1b | 2 | backend | Typed extracted items with per-item match, aliases, units, status enum | 5h | R1a |
| MVP-U1 | 2 | all | Unit vocabulary migration to `dl \| tsp \| tbsp \| g \| pcs` (data, OFF parser, frontend) | 3h | R1b |
| MVP-R2 | 2 | backend | Confirm creates products for new items; expiry/location overrides | 5h | R1b, U1 |
| MVP-C1 | 2 | frontend | BottomSheet and Toast primitives | 5h | — |
| MVP-C2 | 2 | frontend | ConsumptionSheet wired to consume mutation | 6h | C1 |
| MVP-S2 | 3 | frontend | Stock view: urgency sort, location groups, hide inactive, uses `product_name` | 5h | S1 |
| MVP-S3 | 3 | frontend | Quick Add item (product search or new product) | 8h | C1, S1 |
| MVP-S4 | 3 | frontend | Item edit sheet: adjust quantity/expiry/location, mark gone, delete | 5h | C1 |
| MVP-R3 | 3 | backend | Background receipt processing, status transitions, 202 response | 5h | R1 |
| MVP-T1 | 3 | backend | Telegram receipt drop-in bot (share PDF, screenshot or photo from the phone) | 5h | R1a |
| MVP-R3b | 3 | backend | Generic heuristic line-parser fallback when extraction fails | 3h | R1 |
| MVP-R4 | 3 | pipeline | Real-receipt validation on the homelab, LLM settings that finish | 6h | F2, R0, R1 |
| MVP-R5 | 4 | frontend | Receipt types, API module, hooks with status polling | 5h | R1, R2, R3 |
| MVP-R6 | 4 | frontend | Upload page on the iPad: file picker (PDF or image), processing status | 3h | R5 |
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
| DEC-4 | If the R0 spike cannot finish a 60-line receipt: heuristic parser becomes primary with the LLM only categorising; switch model; or accept chunked multi-call extraction | R1, R4 | decide the fallback order now | **not needed**: R0 passed on 2026-09-14 |

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
- [x] **Passed 2026-09-14** (details and working request in `docs/vLLM_MANUAL_TEST.md`,
  harness in `docs/spikes/r0_extraction_spike.py`). On the llama-swap gateway
  (`192.168.0.94:9292/v1`, one RTX 3090 usable), `muse-glimmer` extracted 49/49 products with
  all quantities and weights correct in 40–43 s from text and 47–52 s from a rendered image,
  using compact output keys, `json_schema` and `reasoning_strength: low` (lowest supported value). It is the
  always-loaded model, so no cold load. From text the names were exact (49/49); from a clean
  rendered image ~8 names per receipt were misspelt. Primary path (MinerU OCR → text vs.
  photo → vision) is decided in R4 with real photos once MinerU is back; R1 wires both.

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

#### MVP-R1 — split into R1a, R1b and U1 (operator ruling 2026-09-14)
Rulings: two PRs; category suggested **inline** in the extraction call (a second call on
`muse-glimmer` costs ~40 s); unit conversions `l→dl ×10`, `ml→dl ÷100`, `kg→g ×1000`,
`unit→pcs` (tsp/tbsp only from manual entry); migrating existing `ml` data is its own
increment U1 after R1b, before R2 creates products.

#### MVP-R1a — Extraction layer (branch `feat/mvp-r1a-extraction-layer`)
- [x] Settings: gateway `http://192.168.0.94:9292/v1`, `LLM_MODEL=muse-glimmer`,
  `LLM_MAX_TOKENS`, `LLM_TIMEOUT`, `LLM_REASONING_STRENGTH` (`xhigh|high|medium|low`, empty to
  omit), `MINERU_LANG=latin` (PaddleOCR has no `fi`), `MINERU_TIMEOUT=120` (empty env value
  accepted). Example env files and `docs/DEPLOY.md` updated.
- [x] `llm_extractor.py` rewritten to the R0 request: compact contract
  `{"s","d","p":[{"n","q","w","c"}]}` (since grown `g` in MVP-R2, and `pw`/`sl` in Q2/Q6),
  strict `json_schema` with `c` limited to the DB
  category ids (listed with display names in the prompt), text pre-filter, trailing-price
  stripping, one `LLMExtractionError`. `extract_from_text` and `extract_from_image`. The
  store-hint duplicate and the deprecated flat extraction fields are gone.
- [x] `ocr_service.py`: `OCRUnavailableError` on connect errors, timeouts and 5xx; real
  content type; configurable language; pdfplumber off the event loop.
- [x] Pipeline: PDF → text; image → MinerU text, or the vision model when MinerU is
  unavailable or finds nothing. `ocr_structured` stores `method`, `store_chain`,
  `purchase_date`, `lines`; store and date fill the receipt when the user left them empty.
- Measured before committing to the schema (R0 harness with `s`, `d`, `c` added): 49/49
  products, all quantities and weights, store and date correct; text 45–53 s, vision
  48–52 s; household items get no category, eggs initially did because only ids were listed.

#### MVP-R1b — Typed extracted items with per-item match
- New schema `ExtractedItem` in `schemas/receipt.py`: `name`, `quantity`, `unit`,
  `product_id | None`, `match_score | None`, `match_confidence | None`,
  `suggested_category | None`, `location`, `storage_type`. `ReceiptResponse` exposes
  `items: list[ExtractedItem]` (derived from `ocr_structured.lines`), plus `store_chain` and
  `purchase_date`.
- `ReceiptProcessingService` writes the match result *per item* (today only the count
  survives). Unmatched items keep `product_id = null`.
- Alias-first matching (the general learning mechanism): before RapidFuzz, look up
  `store_product_alias` by normalised `receipt_name` (scoped to `store_chain` when known);
  a hit is `exact`. Alias names also join the fuzzy candidate set so OCR-noise variants of a
  known line still land on the right product. The table and model exist and are unused today.
- Unit normalisation in one backend function with tests: weight lines → `g` (`kg ×1000`),
  volumes → `dl` (`l ×10`, `ml ÷100`), counts → `pcs`. `ExtractedItem.unit` and
  `ConfirmedItemCreate.unit` use it.
- One `ReceiptStatus` enum in `schemas/receipt.py`: `uploaded | processing | completed |
  failed | confirmed`; model default and `crud/receipt.py` use it (today three values disagree).
- `suggested_category` comes from the inline `c` field (R1a). `location` and
  `storage_type` are derived from it (`frozen→freezer`; `pantry`, `condiments`, `snacks`,
  `beverages→pantry`; else `main_fridge` / `refrigerator`); fix the existing map in
  `crud/product_master.py`, which uses non-seeded ids (`seafood`, `bakery`, `grains`).
- Frontend `types/receipt.ts` rewritten to mirror the schema (the current `ParsedProduct`
  type describes fields the backend never produced).
- **Acceptance:** per-item `product_id` and `suggested_category` round-trip through
  `GET /receipts/{id}`; an alias hit wins over a fuzzy candidate; unit normalisation and the
  status enum are covered.
- As built (branch `feat/mvp-r1b-receipt-items`), rulings of 2026-09-14:
  - [x] **Pack sizes are not parsed from names**: a weight line becomes grams, everything else
    pieces (`GLÖGI 1L` ×2 → 2 pcs). Pack size becomes the product default quantity in R2/U1.
  - [x] Pure rule modules: `services/units.py` (`to_canonical`: kg/g → g, l/dl/cl/ml → dl,
    pcs/kpl/unit/st → pcs), `services/storage.py` (category → storage → location, every
    seeded id explicit; unknown → fridge; `crud/product_master.py` and the scanner use it, which
    fixes the non-seeded `seafood`/`bakery`/`grains` ids), `services/store_chain.py`
    (`S-KAUPAT`/`Prisma`/… → `s-group`, `K-Citymarket`/… → `k-group`, else a slug).
  - [x] `MatchingService.prepare()` loads products and aliases once per receipt; `match_line()`
    runs without queries: store alias exact (same chain, then any chain, verified and most
    seen first) → canonical exact → WRatio over canonical **and alias** names keyed by index.
    `MatchResult.source` is `alias | exact | fuzzy | fuzzy_alias`. Aliases are only **read**
    here; R2 writes them on confirm.
  - [x] Each stored line carries `product_id`, `product_name`, `product_storage_type`,
    `match_score`, `match_confidence`, `match_source`; `receipt.store_chain` gets the chain key.
  - [x] `ReceiptStatus` enum everywhere (model default `uploaded`, crud, processing, confirm,
    broadcast type, list filter rejects unknown values with 422). No migration: the column stays
    a string.
  - [x] `ReceiptResponse.items: list[ExtractedItem]` and `extraction_method`, derived from
    `ocr_structured` and tolerant of older shapes. `name_en`/`price` dropped (not extracted).
  - [x] Frontend `types/receipt.ts` mirrors the schema (`ExtractedItem`, `ReceiptStatus`, …).
  - [x] Only matches scoring at least `FUZZY_MATCH_THRESHOLD` (80, previously unused) are stored.
    Found in the end-to-end run: without it `CHEDDAR PUNAINEN` matched `PUNASIPULI` at 50 and
    `LIME` at 60. With it, the rendered receipt kept exactly the three right matches (canonical
    exact, a vision misread at 97.8, a misread alias at 98.2). R7 can still offer weaker
    candidates through `match_all` when the user searches.
  - Known, not fixed here: a failed re-process keeps the previous run's `ocr_structured`, so the
    items of a `failed` receipt can be stale; R3 owns error persistence and retries.

#### MVP-U1 — Unit vocabulary migration
- Alembic data migration for existing rows: `ml → dl` (÷100), `l → dl` (×10), `kg → g`
  (×1000), `unit → pcs`, on `inventory_item`, `product_master.default_unit/default_quantity`
  and `shopping_list_item`.
- `off_service.parse_off_quantity` returns `dl`/`g`/`pcs`; `crud/product_master._unit_type`
  knows `dl`, `tsp`, `tbsp`.
- Frontend `Unit` type becomes `dl | tsp | tbsp | g | pcs`; fixtures and `isCountable`
  updated; quantity display unchanged (it prints the unit string).
- **Acceptance:** migration up/down tested on a copy with mixed units; tsc and all suites green.
- As built (branch `feat/mvp-u1-unit-migration`), rulings of 2026-09-14:
  - [x] **Convert on write**: inventory, product (create and update), shopping list (create and
    update) and receipt-confirm requests accept `ml`, `cl`, `l`, `kg`, `kpl`, `unit`, `st` and the
    canonical units; amounts are scaled and stored canonical; unknown units return 422. Product
    `unit_type` is derived from the unit (`volume | weight | count`). Response schemas never
    convert, so a stray legacy row cannot break reads.
  - [x] **tsp and tbsp are canonical on their own**, never converted to dl.
  - [x] One conversion table in `services/units.py` (`canonical_factor`,
    `to_canonical_decimal`, `unit_type_for`); OFF barcode quantities use it (`1 L` → 10 dl).
  - [x] Data migration `a4f8c2d91e37` scales `consumption_log` (via its item's unit, first),
    `inventory_item`, `product_master` (amounts, unit, unit_type) and `shopping_list_item`;
    unknown units are left and reported. Downgrade only restores `dl → ml` (lossy by design).
    Tested in pytest and up/down/up on a throwaway database with legacy rows.

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
- As built (branch `feat/mvp-r2-confirm-generic-products`), rulings of 2026-09-14:
  - [x] **Products are generic.** SNELLMAN and ATRIA NAUDAN JAUHELIHA are one product; brand,
    fat content and cut do not matter. Names are **English** first (language options later).
  - [x] Extraction contract gains `g` (generic English name, required in the schema) with
    examples in the prompt; the catalog's product names (up to 300) are listed so the model
    reuses them. Stored per line as `generic_name`; `ExtractedItem.generic_name`.
  - [x] Matching: alias of the printed name → exact generic name → exact printed name → best
    fuzzy of generic-vs-products and printed-vs-products-and-aliases (threshold 80).
  - [x] `services/receipt_confirm.py`; the endpoint maps its errors (404, 409, 400). One
    transaction with a row lock on the receipt; any invalid item writes nothing.
  - [x] Items: `index` (line; learns the alias), `product_id`, or `name` (defaults to the line's
    generic name) with `category` (defaults to the line's). A name is reused
    case-insensitively, including within one confirm; new products take shelf life from the
    category, storage from the category mapping, units from the confirmed unit.
  - [x] `expiry_date` (source `manual`) and `location` overrides; default location follows the
    product's storage type.
  - [x] **Only `completed` receipts can be confirmed**; confirmed → 409 "already confirmed",
    others → 409 "not ready". The `200 success: false` error path is gone.
  - [x] Aliases keyed by printed name and chain: created verified, or reinforced
    (`occurrence_count + 1`) and corrected to the chosen product.
  - [x] Broadcasts after commit: `inventory created` per item, then the receipt status.
  - [x] `LLM_MAX_TOKENS` default 8192: the 49-line receipt with generic names used 3758.
  - [x] Frontend types: `generic_name`, `ConfirmedItemCreate`, `ReceiptConfirmRequest`,
    `ReceiptConfirmResponse` (no UI; R7).
  - [x] E2E with `muse-glimmer` recorded in `docs/vLLM_MANUAL_TEST.md`: a second receipt with
    other brands arrived 11/12 pre-matched.

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
- As built (branch `feat/mvp-r3-receipt-queue-worker`), rulings of 2026-09-14:
  - [x] **Postgres queue + one worker service** instead of `BackgroundTasks`: the model serves
    one request at a time, the API runs two uvicorn workers, and the queue must survive
    restarts. `services/receipt_queue.py` (enqueue, FIFO claim with `FOR UPDATE SKIP LOCKED`,
    stale failure, queue position); `app/worker/` (`python -m app.worker`, `kyokki-worker`
    service in both compose files).
  - [x] **Uploads queue automatically** on both channels (`/scan` returns `queued`).
    `/process` returns 202 and only re-queues `failed` or pre-queue `uploaded` receipts; 409 for
    queued/processing ("already queued or processing") and completed/confirmed ("already read").
  - [x] New status `queued`; migration `c3e9a7b5d1f2` adds `queued_at`,
    `processing_started_at`, `error` (last failure, max 500 characters, cleared on success).
  - [x] Stale recovery: `processing` for more than `RECEIPT_STALE_MINUTES` (10) becomes `failed`
    with an error, checked by the worker loop and on `GET /receipts`, `GET /receipts/{id}`,
    `/process`. Settings `RECEIPT_WORKER_POLL_SECONDS` (2) and `RECEIPT_STALE_MINUTES`.
  - [x] Telegram bot: no in-memory processing queue; the handler reports the queue position
    from the database and a `ResultNotifier` edits the acknowledgement when the receipt is
    finished. A bot restart loses only pending message edits.
  - [x] Shared `core/service_runner.py` for SIGTERM handling in the worker and the bot.
  - [x] E2E with `muse-glimmer` (API + worker processes): two uploads answered `queued` in
    281 ms and 32 ms and were read back to back (62 s, then 28 s); a worker killed mid-read
    left the receipt `processing`, back-dated 11 minutes it read as `failed` with the error,
    `/process` re-queued it (202, a second call 409), a restarted worker completed it, and
    `/process` on the completed receipt answered 409.

#### MVP-R3b — Generic heuristic fallback
- When extraction fails or times out, a deterministic, store-agnostic line parser turns
  `NAME … PRICE` lines (with an optional following `n KPL` / `x,xxx KG` line) into
  `ExtractedItem` rows, so `completed` always has rows on the review screen. Marks the receipt
  `extraction_method = "heuristic"` so R7 can show a hint. The grammar in the
  `ARCHITECTURE.md` appendix is the reference; chain-specific rules stay post-MVP.
- **Acceptance:** the 60-line S-kaupat text yields ≥ 80 % of product lines with no LLM
  call; a failing LLM call degrades to heuristic rows rather than `failed`.
- As built (branch `feat/mvp-r3b-heuristic-fallback`), 2026-09-14:
  - [x] `app/parsers/heuristic.py` `parse_receipt_text`: `NAME PRICE [PRICE] [VAT code]`
    product lines, `n KPL` / `n x` quantity and `x,xxx kg` weight lines after them, negative
    prices (leading or trailing minus) skipped as discounts, header store and first valid date.
    Skip list shared with the LLM prefilter (`app/parsers/receipt_lines.py`) and extended with
    deposits, Plussa, Lidl Plus savings and card payment lines.
  - [x] S-kaupat order: 49/49 names, 11/11 quantities, 10/10 weights (fixtures in
    `backend/tests/fixtures/receipts/`, expected values checked against the R0 ground truth);
    K-Group and Lidl appendix snippets parse too.
  - [x] Fallback only when there is text (PDF or OCR): on `LLMExtractionError` or when the
    model returns no lines. Unreadable text or the vision path still fail as before.
    `extraction_method = "heuristic"`, `fallback_reason` stored and returned.
  - [x] `/process` re-queues a completed heuristic receipt (until confirmed) so the model can
    read it later; other completed receipts stay 409. The Telegram summary says when a receipt
    was read without the model.
  - [x] E2E: worker with the gateway unreachable read the S-kaupat PDF in ~4 s as heuristic
    (49 items, 11 quantities, 10 weights, store and date); `/process` with `muse-glimmer` back
    re-read it as `text` (49 generic names, 40 categorised); a second `/process` was 409.

#### MVP-T1 — Telegram receipt drop-in bot
Operator input 2026-09-14: receipts are mostly digital (online grocery order PDFs, S-Group /
K-Plussa app receipts) plus some photos of paper receipts; the phone is Android. The easiest
drop-in is sharing the file to a private Telegram bot from the phone's share sheet, at home or
away, with no port forwarding.
- Separate compose service `kyokki-telegram` running `python -m app.telegram_bot` from the API
  image: Telegram Bot API over `httpx` with `getUpdates` long polling (outbound only, no new
  dependency). Starts only when `TELEGRAM_BOT_TOKEN` is set.
- Settings: `TELEGRAM_BOT_TOKEN` (secret, `stack.env` only, never logged),
  `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated). Messages from other chats are ignored except
  `/start`, which replies with the chat id so setup needs no guessing.
- Accepts documents (`application/pdf`, `image/*`) and photos (largest size). Telegram
  recompresses photos, so the `/start` help says to send paper-receipt photos "as file" for best
  OCR. Files are downloaded with `getFile` (Bot API limit 20 MB) and stored through the same
  path as `POST /api/receipts/scan` (`crud/receipt.create_receipt`).
- Duplicate guard: a SHA-256 of the file content is stored on the receipt (migration adds
  `content_sha256`, indexed); sharing the same file twice replies "already received" with the
  earlier result instead of creating a second receipt.
- Processing: calls `ReceiptProcessingService` (after R3, schedules the background job
  instead). Replies immediately "Received, reading the receipt…", then edits or follows up with
  the result: store, date, `n` items (`m` matched) and a pointer to review on the iPad; on
  failure a short reason. Loyalty-app screenshots are clean images and take the MinerU/vision
  path; PDFs take the pdfplumber text path.
- Privacy note in `docs/DEPLOY.md`: receipts pass through Telegram's servers (they include the
  last card digits); the allowlist keeps the bot private.
- **Acceptance:** tests with a mocked Bot API for allowlist, `/start`, PDF and photo handling,
  duplicate detection and failure replies; manual check sharing an S-kaupat order PDF and a
  loyalty-app screenshot from the Android phone to the bot on the homelab stack.
- As built (branch `feat/mvp-t1-telegram-bot`), rulings of 2026-09-14:
  - [x] **Shared ingest** `services/receipt_ingest.py` for both channels: allowed types (PDF,
    JPEG, PNG, WebP), SHA-256, duplicate lookup; a unique-index race returns the existing receipt.
    Migration `b7d3e5f1a2c4` adds `receipt.content_sha256` (unique, nullable for old rows).
  - [x] **Duplicates rejected on both channels**: `POST /api/receipts/scan` answers 409 with
    `{"message": "Receipt already uploaded", "receipt_id": ...}`; the bot answers "Already
    received" plus the earlier summary when it was read.
  - [x] **Reply** is a summary plus unmatched names: "S-group, 2.1.2026: 49 items, 3 matched.
    New: … (+38). Review on the iPad." Up to 8 names; the "Received" message is edited in place.
  - [x] Package `app/telegram_bot/` (client, messages, handlers, worker, runner). One sequential
    worker because the model serves one request at a time; the acknowledgement reports the queue
    position. Queued jobs are in memory: receipts not read before a restart stay `uploaded`.
  - [x] Token is a `SecretStr`; `httpx`/`httpcore` loggers set to WARNING because Bot API URLs
    carry the token; `TelegramError` messages never include the URL. Strangers get only their
    chat id on `/start`, and their messages are not logged.
  - [x] `kyokki-telegram` service in both compose files (no port; idles without a token);
    `.env.example`, `stack.env.example` and the `docs/DEPLOY.md` "Telegram bot" section.
  - [ ] Manual check with a real bot on the homelab (needs the operator's @BotFather token).

#### MVP-R4 — Real-receipt validation on the homelab
- Run at least five real receipts through the deployed stack via the API. Record per receipt:
  OCR time, LLM time, items extracted, items matched, failures. Append to
  `docs/vLLM_MANUAL_TEST.md`.
- Apply R0's winning settings in `llm_extractor.py`. Whatever works becomes the single
  documented default in `config.py`, `.env.example` and `stack.env.example`. Include OCR
  language as a measured variable.
- Settled 2026-09-16: **the model drift is gone.** `config.py`, `.env.example`,
  `stack.env.example` and `docker-compose.prod.yml` all say `c2.muse-glimmer`,
  `http://192.168.0.94:9292/v1`, MinerU `http://192.168.0.94:8008`, `MINERU_LANG=latin`,
  `LLM_MAX_TOKENS=8192`. Only older design docs still name Qwen; do not chase them.
- Measurement is in place (branch `feat/mvp-p1-r6-r8-app-shell`): every read logs one line with
  `receipt_id`, `ocr_seconds`, `llm_seconds`, `total_seconds`, `method`, `items_extracted` and
  `items_matched`. `JSONFormatter` used to drop unknown extras, so nothing could be timed from
  the logs before this. What is left for R4 is five real receipts and the write-up.
- **Acceptance:** 5/5 receipts reach `completed` in under 120 s each with ≥ 80 % of line
  items extracted. If this cannot be met, stop and file a DEC before building R6/R7.
- Prep done 2026-09-16 (branch `fix/homelab-endpoints-and-generic-naming`): MinerU is back at
  `192.168.0.94:8008` and the gateway now serves per-GPU copies; `c0` is reserved for the
  operator's agent, so the default model is `c2.muse-glimmer`. Compared against `c2.gemma-26b`
  and `c2.qwen3.8-27b` on the real contract: all three extract 49/49 lines, muse-glimmer wins on
  generic-name quality (singular, correct Finnish). Prompt now demands singular names and names
  household products. Numbers in `docs/vLLM_MANUAL_TEST.md`. R4 itself still needs the deployed
  homelab stack.

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
- **Acceptance:** calculation tests (¼ of 10 dl = 2.5 dl; cap when 1 dl left), flow test
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
  - Items with equal expiry dates came back in varying order, so cards swapped places after
    refetches. Resolved in S2 (stable sort on client and server).

#### MVP-S2 — Stock view
- Default query hides `empty` and `discarded`. Sort by `expiry_date` ascending. Group by
  `location` (Fridge / Freezer / Pantry) with counts. "Expiring soon" (≤ 3 days) pinned on top.
- Uses `product_name` from S1; remove the products list fetch from `page.tsx`.
- **Acceptance:** tests for sort, grouping, hiding; visual check in iPad landscape.
- As built (branch `feat/mvp-s2-stock-view`), with the operator ruling of 2026-09-14:
  - [x] `lib/stock.ts` `buildStockView`: hides empty/discarded (so an optimistic Done removes
    the card at once), pins items expiring in ≤ 3 days (expired included) **only** in
    "Expiring soon" (ruling: no duplicate cards), then groups Fridge / Freezer / Pantry and an
    "Other" group for unknown location strings (the API accepts any string). Empty groups hidden.
  - [x] Stable order everywhere: expiry, then `created_at`, then `id`, in `compareStock` and in
    `crud/inventory_item.py` (list and scanner consume). The backend test rewrites rows first,
    because Postgres only reshuffles ties after an UPDATE.
  - [x] `InventoryList` renders labelled sections with count chips, two-column grid from `lg`
    (iPad landscape); grouped cards drop the location from the subtitle, pinned cards keep it.
  - [x] Products fetch, name map and "Could not load product names" banner removed from the
    home page. `hooks/useProducts.ts` stays for S3.
  - Checked in Chrome at 1280 px against the real API: section order and counts, two columns,
    tie order unchanged after a consume rewrote a row, Done on a pinned item removes it.
    Not yet checked on the iPad itself.

#### MVP-S3 — Quick Add item
- "+ Add" opens a BottomSheet: product search (`GET /api/products?search=`) with
  "Create new: <typed name>" fallback that asks for category (from `GET /api/categories`),
  then quantity, unit, location; expiry pre-filled from category shelf life, editable.
- New product → `POST /api/products` then `POST /api/inventory`. `lib/api/categories.ts`,
  `hooks/useCategories.ts`, `hooks/useProducts.ts` create mutation.
- **Acceptance:** add existing and add new both land in the list; validation for quantity > 0.
- As built (branch `feat/mvp-s3-quick-add`), rulings of 2026-09-14:
  - [x] **One backend call** `POST /api/inventory/quick-add` instead of `POST /products` then
    `POST /inventory` (no orphan products, no "milk"/"Milk" duplicates). Takes `product_id` or
    `name` (+ `category` for a new product), quantity, unit (convert on write), optional
    location, purchase date (default today) and expiry (source `manual`).
  - [x] R2's product rules moved to `services/generic_products.py` (`ProductResolver`,
    `build_inventory_item`) and are shared by confirm and quick add. New hand-typed names get a
    capital first letter ("oat drink" -> "Oat drink").
  - [x] `GET /api/categories` returns `default_storage`, so the sheet preselects the location
    without a frontend copy of the mapping.
  - [x] `QuickAddSheet` from "+ Add" on the home page: debounced product search with
    "Create new: <name>", category grid, quantity (must be > 0), unit, location, expiry
    prefilled from shelf life (sent only when edited). Errors keep the sheet open.
  - [x] E2E in Chrome against a throwaway DB: new product, reuse by different case, new frozen
    product with edited expiry landing in the Freezer group, quantity 0 blocked.

#### MVP-S4 — Item edit sheet
- Long-press or "⋯" on a card: adjust current quantity, change expiry date, move location,
  "Mark as gone" (`PATCH status=discarded`), "Delete" (confirmation step, then `DELETE`).
- **Acceptance:** each action has a test; list refreshes; gone items disappear from default view.
- As built (branch `feat/mvp-s4-item-edit-sheet`), rulings of 2026-09-14:
  - [x] "Edit" on each card opens `ItemEditSheet`: quantity (in the item's unit), expiry,
    location, Save (only changed fields), Mark as gone (`status=discarded`, logged once),
    Delete with a confirmation step. Errors keep the sheet open. No long-press: the visible
    button is enough on the iPad.
  - [x] **Delete removes the item and its history**: `consumption_log` FK is now
    `ON DELETE CASCADE` (migration `d5f1b8c2e4a6`). Before this, deleting any consumed or
    discarded item returned 500. "Mark as gone" is the path that keeps history.
  - [x] **A quantity change is a correction, not logged**: 0 makes the item `empty`; lower
    amounts use the consume status rules (shared `apply_quantity_status`); an empty item
    brought back becomes active; above the full amount raises `initial_quantity`.
  - [x] A new expiry date without `expiry_source` becomes `manual`. `InventoryItemUpdate`
    rejects unknown `status`, `location` and `expiry_source` (422).
  - [x] Shared `components/ui/ChoiceGroup` (radio buttons, hidden inputs kept inside labels)
    and `LOCATION_OPTIONS`, used by Quick Add and the edit sheet. Delete removes the item from
    cached lists at once and is never retried.
  - [x] E2E in Chrome: consume ½ then delete (item and log gone), correct to 0 (empty, hidden),
    correct 4 -> 6 pcs + Pantry + expiry (initial 6, manual), mark as gone (one discard log).

#### MVP-R5 — Receipt types, API module, hooks
- `lib/api/receipts.ts`: `scan(file, meta)` multipart upload (do not set JSON content type),
  `get`, `list`, `process` (retry), `confirm`. `hooks/useReceipts.ts`: `useReceipt(id)` polls
  every 3 s while `queued | processing`, stops on `completed | failed | confirmed`; `useReceiptList`,
  `useUploadReceipt`, `useConfirmReceipt` (invalidates inventory lists).
- Status union copied from the single backend `ReceiptStatus` enum; quantity types follow DEC-2.
- **Acceptance:** msw tests including polling stop conditions and multipart body.
- As built (branch `feat/mvp-r5-r7-receipt-review`), 2026-09-16:
  - [x] `lib/api/receipts.ts` (`list`, `get`, `confirm`, `process`) and `hooks/useReceipts.ts`
    (`useReceipt`, `useReceiptList`, `useConfirmReceipt` with `retry: false`,
    `useReprocessReceipt`). Polling lives in pure helpers (`detailPollInterval`,
    `listPollInterval`): 3 s while a receipt is queued or processing, off once it is finished,
    30 s heartbeat for the list. `scan()` waits for R6, which is the only thing that uploads.

#### MVP-R6 — Scan page
- Re-scoped 2026-09-14: the Telegram bot (T1) is the primary drop-in from the phone, so the
  iPad page is a simple fallback upload rather than a camera flow.
- `/scan`: one "Choose a file" input (`accept="image/*,application/pdf"`; the file picker also
  offers the camera), optional store and date, Upload → scan (queued since R3) → navigate to
  `/receipt/[id]`. `ProcessingStatus` shows queued/processing with elapsed time and a failure
  state with retry.
- Client-side downscale before upload (canvas, long edge ≤ 2000 px, JPEG q 0.85); a 12 MP
  camera capture is 3–5 MB and inflates OCR time and prompt length.
- **Acceptance:** tests for the happy path and the failure path; manual test on the iPad.
- As built (branch `feat/mvp-p1-r6-r8-app-shell`), 2026-09-16:
  - [x] `/scan`: one file input (`image/*,application/pdf`), optional store and purchase date,
    Upload. Success goes straight to `/receipt/[id]`, which already shows the reading state and
    polls, so **no separate `ProcessingStatus` component was needed**.
  - [x] `lib/images.ts` downscales a photo to a 2000 px long edge at JPEG q 0.85 before upload
    and returns the original for PDFs, for images that already fit, and on any failure. The
    endpoint has no size limit of its own, so this is the only guard.
  - [x] Uploading a file already in the system opens the receipt that is there instead of
    reporting an error: the 409 carries `receipt_id`. `errorMessage()` in `lib/api/client.ts`
    learned to read an object `detail`, and `APIError.details` now carries it.
  - [x] `apiClient.upload` already existed and was called by nothing; it is now used and tested.

#### MVP-R7 — Receipt review page
- `/receipt/[id]`: one row per `ExtractedItem`: name (editable), quantity + unit (editable),
  matched product with confidence badge or "New product" with category picker
  (pre-filled from `suggested_category`), "Change product" search, include/skip toggle.
  Footer: n items to add, Confirm. On success: toast, invalidate inventory, go home.
- Confirmed receipts open read-only with a summary.
- A receipt with `extraction_method = "heuristic"` shows a hint ("read without the AI model",
  `fallback_reason`) and a "Read again with the model" action (`POST /process`).
- **Acceptance (as built covers all of this but re-matching):** tests for editing, re-matching,
  skipping, payload shape sent to confirm, and the read-only state.

- As built (branch `feat/mvp-r5-r7-receipt-review`), rulings of 2026-09-16:
  - [x] `/receipt/[id]`: one row per read line with the generic name (printed name beneath),
    quantity, unit and a category picker; include/skip per row; sticky footer with "Add n items"
    and the skipped count. A matched line shows "→ product" with its confidence and needs no
    category.
  - [x] **Lines with no category start skipped** and say why; choosing a category includes them.
    Household items stay out unless the cook wants them.
  - [x] Confirm sends `product_id` for matched lines and `name` + `category` for new ones, with
    the receipt's date (today when it has none); success toasts and returns to the stock list.
    Errors (409 included) keep the page with the edits intact.
  - [x] States: reading, failed with "Read again", confirmed read-only, not found. A heuristic
    receipt (MVP-R3b) says so and offers a re-read with the model.
  - [x] `ReceiptsBanner` on the home page: "n receipts waiting to review" links to the newest,
    "Reading a receipt…" while the worker has one, and a failed receipt links to its page.
  - [x] Not built here: per-line search to attach an existing product (needs a catalog first),
    the receipts list (R8) and the iPad upload page (R6); the Telegram bot covers drop-off.
  - [x] E2E in Chrome against a local stack: a 49-line receipt showed 40 included and 9 skipped;
    giving a compost bag a category made it 41; confirm created 41 items from 39 products
    (duplicate names merged), the banner disappeared, the receipt became read-only, and
    consuming an item from the list worked.

#### MVP-R8 — Receipts list
- `/receipts`: recent receipts with status chip, item counts, date; tap opens review. Lets the
  user leave during processing and come back.
- **Acceptance:** list renders all statuses; completed-unconfirmed are visually flagged.
- As built (branch `feat/mvp-p1-r6-r8-app-shell`), 2026-09-16:
  - [x] `/receipts`: store and date, what was read ("41 items, 3 already known") or the failure
    reason, and a `ReceiptStatusChip`. A receipt that has been read but not confirmed says
    **"Waiting for review"** in warning colours; the rest are Reading / Could not read / Added
    to stock. The whole row opens the receipt.
  - [x] **The list response was slimmed** (`ReceiptSummary`): no `ocr_raw_text`, no
    `ocr_structured`, no `items`, plus `limit` (1-200, default 50) and `offset`. The home banner
    polls this endpoint every 30 s, so it was shipping every receipt's full OCR text to the iPad.
  - [x] `ReceiptsBanner` now sends you here when more than one receipt is waiting; a single one
    still opens directly.

#### MVP-P1 — AppShell
- Persistent header/side rail: Inventory, Scan (primary, always visible), Receipts. Remove the
  `/components-demo` link from the header (page may stay for development). Landscape-first
  layout with a two-column inventory grid on iPad width; 44 pt targets everywhere.
- **Acceptance:** navigation tests; every MVP flow reachable within two taps from home.
- As built (branch `feat/mvp-p1-r6-r8-app-shell`), ruling of 2026-09-16 (**left side rail**):
  - [x] `components/layout/AppShell.tsx` in `app/layout.tsx`, so every route has it: Stock,
    Scan, Receipts, 56 pt targets, `aria-current` on the open one, and `/receipt/[id]` counting
    as Receipts. A rail down the left from `lg` (where the stock grid goes two-column), a bar
    across the top below it.
  - [x] Pages keep their own header and their own actions: the home "+ Add" did not move.
  - [x] `app/layout.tsx` gained `viewport: { viewportFit: 'cover' }`. Without it
    `env(safe-area-inset-*)` resolves to 0, so the safe-area padding already written into the
    sheets, the toasts and the receipt footer was doing nothing on the iPad.
  - [x] The "Components" link is gone from the home header; `/components-demo` still answers.
    `/receipt/[id]` now offers "Back to receipts".

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
- As built (branch `feat/mvp-p2-pwa-dark-refresh`), rulings of 2026-09-17:
  - [x] `app/manifest.ts` (`/manifest.webmanifest`) plus `metadata.appleWebApp` and
    `metadata.icons` in `app/layout.tsx`, and a `themeColor` light/dark pair. The manifest asks
    for landscape; **iOS ignores `orientation` for home-screen web apps**, so the mount decides.
  - [x] Icons: a drawn fridge mark, `public/icons/{icon-192,icon-512,apple-icon-180}.png`,
    generated by `frontend/scripts/make_icons.py` (pure stdlib, no dependencies). The stock
    `app/favicon.ico` is gone. Colours and paths live in `lib/brand.ts`.
  - [x] **Reversed the "no committed binaries" ruling**: `ImageResponse`/`next/og` cannot
    prerender on Windows (`fileURLToPath` "Invalid URL" in `@vercel/og`), so `npm run build`
    failed locally though CI would have passed. Three PNGs totalling ~5 kB instead.
  - [x] **`frontend/Dockerfile` now copies `public/`.** Standalone output does not include it,
    so the icons would have 404'd in production. Verified by building the image and listing
    `/app/public/icons`.
  - [x] Inventory polls: `INVENTORY_POLL_MS` 30 s and `staleTime` 10 s on `useInventoryList`.
    Before this only receipts polled, so a wall-mounted iPad showed stale stock indefinitely -
    `ARCHITECTURE.md` already claimed otherwise.
  - [x] **Dark mode now works** (operator ruling: follow the iPad's appearance). Tailwind
    `darkMode: ['variant', ...]` fires on `prefers-color-scheme: dark` and still honours a
    `.dark`/`.light` class; `globals.css` and `color-scheme` follow. 175 `dark:` variants were
    already written and had never once applied.
  - [x] Two latent bugs found by the visual pass: **`lib/` was missing from Tailwind's `content`
    globs**, so class strings built in `lib/` were only generated when a component happened to
    use the same string; and `getExpiryColor` had no dark variants at all.
  - [x] Not done: no service worker, because plain HTTP on the LAN is not a secure context, so
    registration is refused. Confirms rather than changes the post-MVP deferral.

#### MVP-P3 — Acceptance week
- Use it for a week. Scan every receipt, consume from the iPad, fix stock by hand when wrong.
  Log friction in this file under "Post-MVP frontier". Tick the eight acceptance items above.
- Wave H0 of the hardening track below runs before or alongside this week: it removes the
  data-loss and dead-display failures the reviews found, which would otherwise be logged as
  friction and then have to be fixed under acceptance pressure.

### Hardening track — findings of the 2026-09-17 reviews
Five reviews traced every surface at `23b83ad`: `docs/reviews/pipeline-receipt-processing.md`,
`pipeline-receipt-confirm.md`, `pipeline-foundations.md`, `pipeline-foundations-2.md` and
`pipeline-foundations-3.md`. Each finding there has a `file:line` and a failure scenario; the
items here are the PR-sized work that closes them, grouped into waves by what they unblock.
The matching redesign has its own spec, `docs/PRODUCT_RESOLUTION_SPEC.md`; wave H1 is that
spec's PR-1 to PR-7 under stable ids.

How this fits the priority rule: **H0 is MVP work** (the acceptance week cannot be run safely
without it), **H1 repairs MVP-R1b/R2 behaviour** (the matcher pre-selects wrong products and
confirm makes that permanent), and **H2 to H4 come after MVP-P3** unless the acceptance week
hits one of them, in which case that item moves up. The agent track (`docs/agent_TODO.md`)
starts after H2, because it needs the status machine, the vocabularies and the access key.

#### Decisions the track needs (operator-gated)

| ID | Question | Blocks | Recommended | Status |
| --- | --- | --- | --- | --- |
| DEC-5 | Access control for the LAN API: a shared secret header checked on every mutating route and the WebSocket (one env var, sent by the frontend proxy and the CLI), or Traefik forward-auth later, or stay open | H31, AG1 | shared header now; forward-auth when HTTPS lands | open |
| DEC-6 | Next.js major upgrade (14 is unsupported; 1 critical, 2 high on paths this app has): before or after the acceptance week | H33 | right after P3; React 19 and the caching changes should not land during acceptance | open |
| DEC-7 | Scanner and Open Food Facts surface (~700 lines, no frontend caller, three known 500s): quarantine behind a flag, or route through `ProductResolver` now | H41 | quarantine until GS1/barcode work starts | open |
| DEC-8 | Receipt retention: delete the file N days after confirm and keep the structured lines; keep or drop `ocr_raw_text` after confirm | H35 | 90 days, drop the raw text on file deletion | open |
| DEC-9 | Categories: seed-only (remove POST and DELETE, storage stays a code map) or user data (storage becomes a column, delete becomes RESTRICT) | H22 | seed-only | open |
| DEC-10 | Expiry when an item is moved to the freezer: leave the product's shelf life (today: mince frozen on day one reads expired on day six), or a frozen-shelf-life rule per category | none yet | defer; log it in the acceptance week if it bites | open |

#### Wave H0 — before the acceptance week

| ID | Side | Increment | Est. | Closes |
| --- | --- | --- | --- | --- |
| H01 | backend | **Test database isolation.** `conftest` derives `<POSTGRES_DB>_test`, creates it if missing, runs each test in a rolled-back transaction, imports settings lazily; `requires_db` applied automatically from fixture use in `pytest_collection_modifyitems`, the four decorative markers either meaningful or gone | 3h | F2 Critical #1, F3 Critical #2, F3 misjudgement 8 |
| H02 | repo | **Settings and commands that work on the workstation.** `extra="ignore"` in `Settings`; `ENV_FILE` moves to `backend/.env` with `backend/.env.example`; the CLAUDE.md table pins the interpreter (`backend/.venv` via `python -m`); `typecheck` compares against a committed baseline until H21 takes it to zero; the three undocumented settings get example lines | 2h | F1 Important (settings echo values), F3 Critical #2, F3 Minor (env examples) |
| H03 | infra | **Deploy runbook and liveness.** `--env-file` on the Telegram steps, the volumes claim fixed, `/health` checks Postgres and Redis with a 1 s budget, `kyokki-api` gets a healthcheck and `frontend` waits on it, `TZ=Europe/Helsinki` on every backend service | 2h | F3 Critical #1, F2 Minor (`/health`), F1 Minor (healthcheck, TZ) |
| H04 | frontend | **The display cannot go blank.** `error.tsx` and `global-error.tsx`; `StatusBadge` and every vocabulary-indexed map render unknown values as their raw string; `normalizeInventoryItem` narrows at the API boundary | 3h | F2 Critical #3, F1 Minor (no error boundary), F2 misjudgement 2 |
| H05 | backend | **No 500 on a reachable route.** Shopping and categories under `handle_integrity_errors`; product and category DELETE answer 409 naming what references them; OFF category ids mapped to seeded ids | 3h | F1 Critical #1-#3, F2 Critical #2 |
| H06 | frontend | **Green, not flaky.** Fake timers around the search debounce, `findBy` timeouts above debounce plus msw latency, `--detectOpenHandles` to find the leaked worker, real sleeps removed | 2h | F3 Critical #3, F3 Minor (sleeps) |
| H07 | backend | **Receipt pipeline seams.** `enqueue` is a conditional `UPDATE … WHERE processing_status IN (…)`; `/process` may re-read a completed receipt with zero lines; an image-only PDF goes through OCR then vision; the stored extension comes from the validated content type (also closes the NUL/long-suffix 500); upload byte cap at the API | 4h | Processing Important #1-#2, Confirm Important #1, F3 Minor (suffix) |
| H08 | both | **A receipt can always be finished.** Confirm with zero included lines is allowed and dismisses the receipt; a remembered non-food line that the cook includes with an `index` deletes its `non_food_name` row; only lines the cook has seen folded are sent as `non_food_indexes` | 3h | F1 Important (undismissable), Confirm Important #2 |

#### Wave H1 — product resolution (`docs/PRODUCT_RESOLUTION_SPEC.md`)

| ID | Spec | Side | Increment | Est. | Depends on |
| --- | --- | --- | --- | --- | --- |
| H11 | PR-1 | backend | `product_name` table (canonical plus synonyms), unique normalised canonical name after a dedupe migration, `ProductResolver` resolves by name, confirm learns synonyms | 4h | — |
| H12 | PR-2 | backend | `line_id` and `resolution` on stored lines; `ExtractedItem.match_source` becomes alias/name/selected/none plus `verified`; old blobs tolerated and tested | 3h | — |
| H13 | PR-3 | backend | `product_resolution.py`: deterministic tiers, `pg_trgm` candidate retrieval, one selection call per receipt validated against the offered candidates; fuzzy decision path, `match_all`, `match_product` and `FUZZY_MATCH_THRESHOLD` removed | 8h | H11, H12 |
| H14 | PR-4 | backend | Alias provenance (`source`), unique (chain, printed name), the learning table from spec 3.4, precedence verified before unverified | 3h | H13 |
| H15 | PR-5 | frontend | Review row: provenance chip (known / auto), **Change** control on the existing product search with a "New product" entry, detach | 6h | H12, H14 |
| H16 | PR-6 | backend | `POST /products/{id}/merge`; FKs to `product_master` become RESTRICT with a 409 naming the references (DEC-9 for categories) | 4h | H11 |
| H17 | PR-7 | pipeline | Catalog list leaves the extraction prompt behind a setting; measured on the 49-line fixture; default once quality holds | 2h | H13 |
| H18 | — | both | **Product editor**: rename, piece weight, shelf life, opened shelf life, unit; the Q2/Q4 leftover, and the only safe answer to a wrong first guess | 5h | H16 |

#### Wave H2 — foundations: state, schema, types, dates

| ID | Side | Increment | Est. | Closes |
| --- | --- | --- | --- | --- |
| H21 | backend | **Typed models.** `Mapped[]` and `DeclarativeBase`, the `row: Any` casts removed, mypy baseline to zero, CI gate fails on lint and type | 6h | F1 Important (CI gate), F1 misjudgement 4 |
| H22 | backend | **Delete semantics.** Every FK gets an explicit rule (RESTRICT with 409, or cascade where history belongs to the parent); category API per DEC-9 | 3h | F1 Critical #1-#2, F1 misjudgement 5, F2 Minor (spices) |
| H23 | backend | **One status machine.** `transition(item, event)` with an allowed-transition table: discard freezes quantity and blocks writes, correction above full re-labels, create enforces `current ≤ initial`, consume quantised to 2 dp with a unit and a zero-result refused, expiry ≥ purchase; `SELECT … FOR UPDATE` on consume and update | 6h | F1 Important (lost update), F2 Important #1-#2, F2 Minor (create, consume, expiry), F2 misjudgement 1 |
| H24 | both | **Closed vocabularies.** One `StrEnum` per vocabulary (inventory status, expiry source, location, shopping priority and source) used by the schemas and the crud rules; the TS types regenerated or checked against the schemas in CI (`avg_piece_grams` added, phantom list params removed) | 3h | F1 Minor (free strings, types drift), F2 misjudgement 2 |
| H25 | frontend | **One source of truth while a sheet is open.** Edit sheet diffs against the mounted snapshot; quick add derives location and unit from the resolved product, never from the chosen category, and hides "Create new" while the search is pending; the consumption mirror either follows the opened clock or stops predicting expiry | 4h | F2 Important #3, F2 Minor (quick add), F1 misjudgement 6 |
| H26 | backend | **An honest model boundary.** Every failure at the boundary is an `LLMExtractionError` with a kind (transport, format, truncated); JSON found with `raw_decode`, `finish_reason == "length"` stored as such, `w`/`q` coerced like `pw`/`sl`, receipt text fenced as data | 3h | F2 Important (non-httpx errors), F2 Minor (extractor), F2 misjudgement 5 |
| H27 | backend | **A structural heuristic parser.** A skipped line resets the current product, weights accept 1-3 decimals, `säästö` anchored to the loyalty forms, tests on the fixtures for each | 2h | F2 Important (deposit count), F2 Minor (parser) |
| H28 | both | **Dates have an owner.** The client sends `opened_date`, `purchase_date` and the "today" it used; the server validates and stores; `dates.ts` parses `YYYY-MM-DD` as local; the expiry badge and the quick-add default agree with the server | 3h | F1 Minor (two clocks), F1 misjudgement 8 |

#### Wave H3 — exposure, dependencies, retention

| ID | Side | Increment | Est. | Closes |
| --- | --- | --- | --- | --- |
| H31 | both | **The LAN is not the boundary** (DEC-5). Shared secret header on every mutating route and the WebSocket handshake, `Origin` checked on the WebSocket, the upload route behind the same header, `API_PORT` no longer published by default (the frontend proxy is the door) | 4h | F3 Important (WebSocket, upload), F3 misjudgement 5, F1 Minor (API_PORT) |
| H32 | repo | **Reproducible builds.** `uv lock` or `pip-compile` for the backend, exact pins for React and react-query, `pip-audit` and `npm audit --omit=dev` in CI, dev dependencies out of the prod image, `.dockerignore` in both packages, non-root user | 3h | F3 Important (unpinned), F2 Minor (Dockerfiles), F1 Minor (root) |
| H33 | frontend | **Next.js 15/16** (DEC-6): React 19, async request APIs, caching defaults; the rewrite and the standalone Dockerfile re-verified; audit clean | 8h | F3 Important (Next 14 line) |
| H34 | backend | **Bounded work per receipt.** Page cap and byte cap before parsing, pdf parsing in a subprocess with a timeout, Redis client with socket and connect timeouts, broadcasts fire-and-forget with a timeout | 4h | F3 Important (large PDF), F1 Minor (Redis), F3 misjudgement 6 |
| H35 | both | **Things can be forgotten** (DEC-8). `DELETE /receipts/{id}`; a retention job that deletes the file N days after confirm; the Redis-listener log line carries type and id only; log rotation and a `pg_dump` plus `kyokki_data` backup script in the runbook | 4h | F3 Minor (retention, log payload), F1 Minor (backup), F3 misjudgement 7 |
| H36 | operator | **Rotate and purge.** Postgres password and gateway key rotated on the homelab; `stack.env` purged from the public history (open since MVP-F1) | 1h | F3 Important (history) |

#### Wave H4 — scanner, tests, docs, hygiene

| ID | Side | Increment | Est. | Closes |
| --- | --- | --- | --- | --- |
| H41 | backend | **Scanner quarantine or repair** (DEC-7). Quarantine: `SCANNER_ENABLED=false` leaves the router unmounted and its tests behind a marker. Repair: route through `ProductResolver`, validate quantity > 0, fail the scan when the mode cannot be read, mode state in Postgres | 3h / 8h | F1 Important (scanner), F2 Important (scanner), F1 misjudgement 7, F2 misjudgement 4 |
| H42 | backend | **Concurrency and tolerance tests.** Two sessions under `asyncio.gather` for `claim_next`, confirm and consume; `items_from_structured` on pre-R1b blobs; `requires_mineru` instead of bare skips; the Ollama integration tests deleted and the CI integration job made blocking | 4h | F3 Important (locks untested), F3 Minor (markers) |
| H43 | docs | **One owner for status.** The sprint block owns what is built; the ARCHITECTURE as-built note rewritten and pointed at it; README features trimmed to what exists; the two style profiles rewritten for this codebase or deleted; SETUP_SUMMARY deleted; FRONTEND_PLAN and SCANNER_ARCHITECTURE get status banners; CLAUDE.md rules either made true (products and categories broadcast, categories use `handle_integrity_errors`, shopping validation moves to the schema) or reworded, with a grep check per rule in CI | 3h | F3 Important (docs), F3 misjudgements 1-2, F3 Minor (rules, layout, stale docs) |
| H44 | repo | **Line endings.** `.gitattributes` with `* text=auto eol=lf`, one normalising commit | 1h | F3 Minor (CRLF) |
| H45 | frontend | **A status surface for an unattended display.** A persistent banner for last sync, worker or gateway unreachable, and failed actions with a retry chip; toasts stay for the happy path; icon buttons named with the product; sheet focus lands on the primary action; empty-stock copy names the real ways in | 4h | F2 Minor (toast, a11y, copy), F2 misjudgement 8 |
| H46 | backend | **A consumption history that can be read back.** Event vocabulary (consume, correct, discard, restore), `consumed_at` written, corrections logged, `meal_contexts` wired or dropped; prerequisite for post-MVP item 8 | 3h | F2 misjudgement 8 (log), F2 Minor (dead fields) |
| H47 | backend | **Telegram hygiene.** Exit non-zero on the 409 conflict from a second instance, `failure_text` without gateway internals, a separate dev token documented | 1h | F2 Important (two instances), F2 Minor (failure text) |

Report keys: Processing = `pipeline-receipt-processing.md`, Confirm = `pipeline-receipt-confirm.md`,
F1 = `pipeline-foundations.md`, F2 = `pipeline-foundations-2.md`, F3 = `pipeline-foundations-3.md`.

### Post-MVP frontier (do not start before MVP-P3)
**First after MVP-P3: agent interface track** (`docs/agent_TODO.md`, AG0–AG7, planned
2026-09-14). A Hermes Agent or OpenClaw agent adds and consumes stock, creates generic products
and aliases, explores and cooks recipes, and builds shopping lists through the HTTP API, a
`kyokki` CLI with `-h` help and a SKILL.md. No MCP server. Recipes come from Mealie or an
alternative chosen in the AG0 spike against HowToCook granularity. It absorbs parts of items 5,
6 and 8 below: name-based consume is shared with Home Assistant, and shopping-list generation.

Ordered by expected value once MVP is live.
1. WebSocket live updates in the PWA (`services/websockets.py` already broadcasts). Needs H25
   first: with push updates, a sheet holding a stale snapshot turns every edit into a lost
   update. Also needs H31: the WebSocket has no origin check today.
2. ~~"Opened" tracking~~ — done as Q5 (PR #49): consuming from sealed sets `opened_date` and
   the opened clock shortens expiry.
3. GS1 DataMatrix parser (`backend/app/services/gs1_parser.py` — no stub exists yet).
4. Traefik + HTTPS, service worker, offline queue.
5. Shopping list UI (API done, PR #14), minimum-stock auto-add.
6. Home Assistant REST endpoints (`HOME_ASSISTANT_SPEC.md`).
7. Barcode scanning in the PWA camera; Raspberry Pi scanner station.
8. Multi-receipt batch, consumption learning, analytics. (Mealie recipes moved to the agent
   track's AG0/AG5; meal plans stay here.)
9. Learned store templates (`ADAPTIVE_PARSER_SPEC.md`): chain-specific parse rules that
   skip the LLM for known formats. Generalising accelerator, not a core dependency.
10. More receipt drop-in adapters: e-receipt e-mail (IMAP) ingestion, a watched folder, and the
    Kyokki PWA as an Android share target. MVP covers the Telegram bot (T1) and iPad upload (R6).
11. Runtime simplification for single-node installs: one uvicorn worker with in-process
    broadcast, Redis optional (scanner mode state moves to Postgres).
12. Undo for consume: a backend endpoint that reverses a consume (quantity, status,
    `opened_date`) and removes its `consumption_log` row, then an Undo action on C2's toast.
13. Product name languages: generic names are English since MVP-R2; offer Finnish (or any
    language) names, e.g. a per-product display name or translation at extraction time.

#### Operator friction log — the quantity and consumption model is too crude (2026-09-16)
Renamed F1-F6 -> **Q1-Q6** on 2026-09-17: `MVP-F1` and `MVP-F2` already exist in Wave 1, and
`DEC-3`'s Blocks column says a bare `F2` meaning the deployable stack.
Raised while MVP-P1/R6/R8 was in flight. These six belong together: today a product carries one
unit and a category-wide shelf life, and consuming offers the same buttons whatever the item is.
**Not before MVP-P3**, and "cooking staples" (flour, salt, oil as pantry constants) is explicitly
*not* now.

- **Q1 — Keep non-food off the stock list.** Towels, compost bags and cleaning supplies should
  not enter the food inventory by default. Partly covered: MVP-R7 starts a line with no category
  skipped, and the extraction prompt names household products. What is missing is the system
  *knowing* a line is non-food rather than leaning on a missing category, so the cook is not
  asked about the same paper towels every week.
- **Q2 — Count fruit and veg in pieces, not grams.** A receipt says 1000 g of apples; the cook
  eats apples one at a time. Store a per-product average piece weight (~125 g for an apple) and
  convert at confirm, so stock reads "8 apples". A rough estimate is enough.
- **Q3 — Remember the right unit per product, not per category.** A small yoghurt is a piece; a
  1 kg tub is a weight. The unit belongs to the product (and possibly to the pack size), and the
  system should learn it from how the cook actually logs and consumes it.
- **Q4 — Consumption options that fit the item and the stock on hand.** C2 ships ¼ ½ ¾ Done for
  measured units and −1 −2 −3 Done for pieces, with no idea what the item is. For 8 apples the
  common case is one apple: a large "eat 1" with smaller 2/3/… beside it. The options should be
  derived from the item, its unit and how much is left.
- **Q5 — Opened versus unopened should drive shelf life.** Already on this list as item 2
  (`opened_date` + `opened_shelf_life_days`); F5 is the same ask from the kitchen side and
  raises its priority. Matters most for the big packs.
- **Q6 — Shelf life per produce, not per category.** `default_shelf_life_days` is a category
  constant today, so bananas and carrots expire together. Needs per-product defaults, seeded
  with sensible values and correctable by hand.

##### Q1 as built (branch `feat/q1-non-food`), rulings of 2026-09-17
- [x] **The model's "household" answer is captured instead of discarded.** It is a *sentinel* in
  the `c` enum, not a thirteenth category - a category would be a legal pick on the review
  screen and would put towels *into* stock. `ExtractedLine.non_food` carries it.
- [x] **`non_food_name`** (migration `f3b8c1d4e207`) remembers printed names the cook has said
  are not food, keyed like `store_product_alias` - normalised printed name plus store chain -
  but in its own table, because an alias points at a product and a towel has none.
- [x] A line is marked non-food when **either** the model says household **or** the printed name
  is remembered. That second half is what makes it stick when the model wavers, and it is the
  half that was actually provable: with the gateway down the heuristic parser produced 49
  unflagged lines and the memory still flagged `KOMPOSTOINTIPUSSI PAPERI` and `SIENILIINA`.
- [x] Confirm gains `non_food_indexes`. **Only lines the cook leaves marked are remembered** - an
  ordinary skip teaches nothing, because not buying something is not the same as saying it is
  not food.
- [x] The review screen folds them into the footer: "2 household items · Compost bag, Cleaning
  cloth · Show". Expanding puts them back as ordinary rows, and giving one a category drops it
  from `non_food_indexes`, so the cook beats the model.
- [ ] **Not verified: the model actually answering `household`.** The llama-swap gateway at
  `192.168.0.94:9292` went down mid-verification and never came back, so every live run fell to
  the heuristic parser. The sentinel is covered by unit tests only. **Check the category count
  on the first real receipt after deploying** - the baseline is 40 of 49, and this contract has
  moved it before.

##### Q4 + Q5 as built (branch `feat/q4-q5-consume-and-opened`), rulings of 2026-09-17
- [x] **Q4.** `consumptionOptions` derives the buttons from the item. Pieces lead with a large
  `1` and offer only counts smaller than what is left, then `All n`; there are no disabled
  buttons to read past. Measured things keep quarter/half/three-quarters but are labelled with
  the amount (`½ · 500 dl`), and a fraction that would finish the item is dropped rather than
  shown three times over. `ConsumptionOptionKey` is open now, and the sheet renders the primary
  option full width.
- [x] **Q5.** The contract gains `os` (days it keeps once opened); it rides the same path as
  `pw`/`sl` onto `product_master.opened_shelf_life_days`, which existed as a column and was
  read by nothing. Opening an item now brings its expiry in to
  `opened_date + opened_shelf_life_days`, and **only ever inwards** - a jar opened the day
  before its printed date does not gain a fortnight.
- [x] **Loose produce is not a pack.** The guard is the *piece weight*, not the unit: a milk
  carton is stored as `1 pcs` too, so gating on `pcs` would have exempted every carton and jar.
  Taking one apple from a bowl of thirteen opens nothing. The model agrees - it returned no
  `os` for any of apple, banana, carrot, lime, mango, onion, pear or tomato.
- [x] `avg_piece_grams` is exposed through the product schemas at last; Q2 stored it but the
  API could neither read nor write it.
- [ ] Still not done: the product editor. Q2 deferred it, Q4 was meant to bring it, and this
  increment went to Q5 instead. A wrong piece weight still cannot be corrected except by
  deleting the product.

##### A production bug found while verifying this (2026-09-17)
**Every category came back null, 0 of 49**, with code byte-identical to `main`. The cause was
not this increment: the model answers `"Dairy"` for the id `dairy`, and `parse_completion`
compared case-sensitively, so every category was discarded and confirm could create nothing.
The strict `json_schema` enum is meant to prevent this and the gateway no longer enforces it -
the homelab's llama-swap config has grown a lot of new entries since 2026-09-16. Matching is
case-insensitive now, and 40 of 49 categories came back. **This would have broken the deployed
stack silently**, so it is worth deploying even on its own.

##### On the cost of the extraction contract
The earlier "+27 % for `pw` + `sl`" was one sample against another. Measured again on the same
49-line receipt with three estimate fields: **67.4 s**, against 76.5 s for two fields and 60.2 s
for none. Run-to-run variance swamps the difference, so treat the contract's cost as roughly
60-77 s per receipt and stop reading single runs as trends.

##### Q2 + Q3 + Q6 as built (branch `feat/q2-q3-q6-product-defaults`), rulings of 2026-09-17
The knowledge comes from the model at extraction time (operator ruling), not a seed list.

- [x] The contract gains two per-line fields: **`pw`** (grams per piece, null when counting
  pieces makes no sense) and **`sl`** (typical shelf life in days), with examples in the prompt
  beside the existing R2 naming rules. The heuristic parser leaves both `None`.
- [x] **One migration** (`e7a4c9d2b810`), one nullable column: `product_master.avg_piece_grams`.
  `default_unit` and `default_shelf_life_days` already existed — they were copied from the
  category at creation and then never revisited, which was the actual bug.
- [x] A new product keeps the model's estimates; **a later receipt fills in what is missing but
  never overwrites what is known**, so a correction survives the weekly shop. Knowing a piece
  weight makes the product's unit `pcs` whatever the receipt printed (Q3).
- [x] `quantity_for_product` in `generic_products.py` converts on write — it is the one seam
  both confirm and quick add pass through, and the only place holding the resolved product. The
  arithmetic (`grams_to_pieces`) lives in `units.py`.
- [x] The review row shows the conversion (`KG OMENA GOLDEN · 1.072 kg → 9 pcs`) with the
  quantity and unit still editable, so a wrong guess is a two-tap fix.
- [x] Measured on the 49-line S-kaupat receipt: **still 49 items**, piece weights on 7 lines,
  shelf lives on 39, 5 produce lines converted (13 apples, 12 tomatoes, 3 bananas, 3 onions).
  Per-product shelf lives now differ from their category (carrot 21 d vs the category's 5).
  **Cost: 76.5 s of model time against a 60.2 s baseline, +27 %** — still inside R4's 120 s bar,
  but it is a real price for the two fields.
- [ ] **Not done, and it bites:** nothing corrects a product's piece weight afterwards. Editing a
  review row fixes that purchase, not the product, so a bad estimate keeps being applied. The
  product editor is **H18** in the hardening track. Deleting the product is *not* an escape
  hatch: any product that has been on a receipt has an alias row and the delete is a 500
  (`pipeline-foundations.md`, Critical #1); H05 turns that into a 409 and H16 adds merge.
- [ ] Also seen: the model gives no piece weight to mango or pomegranate, so those stay in grams.
  Arguable either way; the prompt's examples are apple, banana, onion and tomato.

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
- [x] PWA manifest / Home Screen — **MVP-P1, MVP-P2**; offline deferred (needs TLS first)

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
- [x] "Mark as Gone" — MVP-S4 edit sheet (button, not a swipe)
- [ ] "Clear All Expired" batch action
- [x] Quick quantity adjustment UI — MVP-S4 edit sheet
- [x] "Just Bought" manual add flow — MVP-S3 Quick Add

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
- Wave 1: [x] F1 (PR #24; operator rotation + history purge still open)  [x] F2 (PR #26; homelab verification pending)  [x] R0 (passed 2026-09-14, `muse-glimmer`)
- Decisions: [x] DEC-1 (`dl|tsp|tbsp|g|pcs`)  [x] DEC-2 (JSON number)  [x] DEC-3 (same-origin rewrite, shipped in F2)  [x] DEC-4 (not needed, R0 passed)
- Wave 2: [x] S1 (PR #27)  [x] R1a (PR #32)  [x] R1b (PR #34)  [x] U1 (PR #35)  [x] R2 (PR #37)  [x] C1 (PR #28)  [x] C2 (PR #29)
- Wave 3: [x] S2 (PR #30)  [x] T1 (PR #36)  [x] S3 (PR #39)  [x] S4 (PR #41)  [x] R3 (PR #38)  [x] R3b (PR #42)  [ ] R4 (measurable now; needs 5 real receipts)
- Wave 4: [x] R5 (PR #45)  [x] R6 (PR #46)  [x] R7 (PR #45)  [x] R8 (PR #46)
- Wave 5: [x] P1 (PR #46)  [x] P2 (PR #47)
- Friction Q1-Q6: [x] Q2/Q3/Q6 (PR #48)  [x] Q4/Q5 (PR #49)  [x] Q1 (PR #50)  [ ] product editor (now H18)
- Reviews 2026-09-17: five reports under `docs/reviews/`, hardening track H0-H4 added above, `docs/PRODUCT_RESOLUTION_SPEC.md` written
- Hardening H0 (before P3): [x] H01 (PR #52)  [x] H02 (PR #52)  [x] H03  [x] H04  [x] H05  [x] H06  [x] H07  [x] H08 — H01/H02 merged; H03-H08 in PRs #53-#56, all opened 2026-09-18
- Decisions: [ ] DEC-5 access  [ ] DEC-6 Next.js  [ ] DEC-7 scanner  [ ] DEC-8 retention  [ ] DEC-9 categories  [ ] DEC-10 freezer expiry
- Wave 6: [ ] P3 acceptance (with H0)
- Hardening H1 resolution: [ ] H11  [ ] H12  [ ] H13  [ ] H14  [ ] H15  [ ] H16  [ ] H17  [ ] H18
- Hardening H2-H4: after P3, before the agent track

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
