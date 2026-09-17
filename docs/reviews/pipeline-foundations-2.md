# Pipeline Review: foundations, round 2 (previously unreviewed surfaces)

Reviewed at 23b83ad (same tree as origin/main e233db5, 2026-09-17).

Scope: everything the first three reports did not cover. Backend stock surfaces (inventory,
quick add, categories, shopping, WebSocket, health, schemas, crud and their tests); the
integrations (scanner and Open Food Facts, Telegram client and runner); the heuristic parser
run against the fixtures and the model boundary in the extractor; the test, build and image
foundations; the migrations; and the frontend screens themselves (stock view, the three
sheets, shell, PWA, accessibility, test quality). Gathered by three readers plus a core pass
and cross-checked; the four headline claims (test fixture drops tables, shopping 500, badge
crash, stale edit overwrite) were verified directly in the code.

Earlier reports still stand and are not repeated: `pipeline-receipt-processing.md`,
`pipeline-receipt-confirm.md`, `pipeline-foundations.md`.

## Flow
Surfaces read: api/endpoints/{inventory,categories,shopping,websockets,health,scanner}.py,
schemas/*, crud/*, services/{quick_add,units,storage,scanner_service,off_service}.py,
parsers/*, services/llm_extractor.py (boundary only), telegram_bot/{client,runner}.py,
tests/conftest.py, pytest.ini, alembic/versions/*, .github/workflows/images.yml, both
Dockerfiles; frontend app/*, components/inventory/*, components/ui/*, components/layout/*,
lib/{stock,consumption,images,dates}.ts, hooks/useInventory.ts, and the tests beside them.

## Critical (must fix)
- [ ] backend/tests/conftest.py:110-135 — **The backend test suite drops every table in
      whatever database the settings point at.** `db_engine` runs `create_all` then `drop_all`
      on `settings.DATABASE_URL`; the docstring says it uses the same instance as dev. CI sets
      `POSTGRES_DB=kyokki_test`; a workstation `.env` points at the compose stack's `kyokki`.
      Scenario: `docker compose up` holds scanned receipts and stock, the developer runs
      `test-backend`, and after the first DB-backed test every table is gone. Not a crash, but
      irreversible data loss on a documented command. Fix: derive a `<db>_test` name in
      conftest (create it if missing) and run each test in a rolled-back transaction.
- [ ] backend/app/api/endpoints/shopping.py:126,168, backend/app/api/endpoints/categories.py,
      backend/app/crud/base.py:35-61 — **Shopping and category routers have no integrity
      handling at all** (zero uses of `handle_integrity_errors`, against 2-4 in every other
      router). `POST /shopping` or `PATCH` with a `product_master_id` that does not exist is a
      `ForeignKeyViolationError` → 500. `CRUDBase` commits inside and maps nothing.
- [ ] frontend/components/ui/Badge.tsx:109-124, frontend/components/inventory/InventoryItemCard.tsx:71
      — **One unknown status value takes down the whole stock page.** `statusConfig[status]` is
      indexed with no guard, so `config.variant` throws for anything outside the five known
      strings, and the card renders the badge for every item. The API stores whatever
      `POST /inventory` sends for `status` (free-string vocabularies, first foundations
      report), so one row with `status: "gone"` from a manual call, a legacy value or the
      agent track later blanks the always-on display until someone reloads it; there is no
      error boundary. The location label two lines up already defends against unknown values.

## Important (should fix)
- [ ] backend/app/crud/inventory_item.py:179-182,255-294 — **Discard does not freeze the
      item.** `status="discarded"` logs the remaining quantity but leaves `current_quantity`,
      and neither consume nor correction checks status. Consume or PATCH a discarded 750 g pack
      and `apply_quantity_status` flips it back to `partial`; it reappears in stock with a
      history saying it was thrown away, and a second discard logs the remainder again.
      Reachable through the API today and through any second device.
- [ ] backend/app/crud/inventory_item.py:184-193,140-157 — **Raising a partial or opened item
      above full keeps the old label.** Item 200/1000 `partial`, PATCH `current_quantity=1200`
      → both quantities become 1200, status stays `partial` (only `empty` is rescued). The bar
      shows 100 %, the badge says partial, and the next consume measures from 1200 as full.
- [ ] frontend/components/inventory/ItemEditSheet.tsx:42-54, frontend/app/page.tsx:26 — **A
      stale edit form overwrites a fresher quantity.** The sheet copies the item into state at
      mount but diffs against the live item on every render. Milk shows 10 dl, the cook opens
      Edit, a consume from the phone (or the 30 s poll) brings it to 5 dl, the cook changes only
      the location and saves: the diff sees 10 ≠ 5 and sends `current_quantity: 10`, silently
      undoing the other consume. Diff against the mounted snapshot.
- [ ] backend/app/parsers/heuristic.py:85-98 — **Quantity lines bind to the previous product
      across skipped lines.** Reproduced on `Karhu 6-pack 12,00` / `Tolkkipantti 0,90`
      (skipped) / `6 KPL 0,15 €/KPL`: the beer gets quantity 6 from the deposit's count line.
      K-group receipts print a count line after every deposit, so multipacks are mis-quantified
      silently on the one path that carries no confidence signal. A skipped line must reset the
      current product.
- [ ] backend/app/services/llm_extractor.py:254-296 — **Only httpx errors become
      `LLMExtractionError`, so the heuristic fallback is bypassed for every other failure.**
      A 200 with an empty or HTML body raises `JSONDecodeError`; a gateway that returns
      `content` as a list of parts makes `_THINK.sub` raise `TypeError`; both escape
      `_read_text`'s `except LLMExtractionError` and the receipt is `failed` although its text
      was readable. Wrap the whole boundary.
- [ ] backend/app/api/endpoints/scanner.py:33-37, backend/app/services/scanner_service.py:52-91,285-307
      — **Scanner quantity is unbounded and the mode falls back to `add` on any Redis error.**
      `{mode: consume, quantity: -5}` computes `current - (-5)` and stock rises with a
      `use_partial` log of -5; `quantity: 0` in add mode hits `InventoryItemCreate(gt=0)` inside
      the service → 500. `get_mode` swallows every Redis error and returns the default, so a
      Redis restart (no persistence) turns a consume station into an add station with no error.
      Post-MVP surface, reachable now.
- [ ] backend/app/telegram_bot/runner.py:41-54 — **Two bot instances with one token fight
      silently.** Telegram answers `getUpdates` with 409 Conflict when another long-poll is
      active; the loop treats it as transient, backs off to 60 s and retries forever, each
      instance winning some updates. The documented dev command (`python -m app.telegram_bot`)
      alongside the deployed `kyokki-telegram` sends receipts to whichever database won the
      poll. Detect the 409 description and exit non-zero.

## Minor
- [ ] backend/app/schemas/inventory_item.py:15-16 — `POST /inventory` accepts
      `current_quantity > initial_quantity`; status stays `sealed`, the bar shows 500 %, and the
      status machine never opens it.
- [ ] backend/app/schemas/consume.py:11 — `ConsumeRequest.quantity` is an unquantised
      `Decimal` with no unit: consuming `0.004` on 1000 g sets `opened`, starts the opened clock,
      then Postgres rounds the column back to 1000.00 and the log row to 0.00.
- [ ] backend/app/api/endpoints/shopping.py:142-181,262-275,22,89 — PATCH `is_purchased: true`
      never sets `purchased_at`; `DELETE /shopping/purchased/all` broadcasts nothing while
      single deletes do; routes are declared at `"/"` so `/api/shopping` answers 307.
- [ ] backend/app/api/endpoints/categories.py:35-46, backend/app/services/storage.py:325-353 —
      categories can be created through the API but storage is a code map keyed by seeded ids:
      a cook-added `spices` category files every spice and its stock in the fridge.
- [ ] backend/app/services/quick_add.py:39-46, backend/app/schemas/inventory_item.py:66-69,92 —
      `expiry_date` is never checked against `purchase_date`; a year typo on the date picker
      creates an item that sits at the top as expired with no error.
- [ ] backend/app/api/endpoints/health.py:6-11 — `/health` touches neither Postgres nor Redis,
      so the compose healthcheck the first report asked for would pass with the database down.
- [ ] backend/app/models/inventory_item.py:55, backend/app/models/category.py — `consumed_at`
      and `meal_contexts` are exposed on every response and written or read by nothing; the TS
      types mirror them.
- [ ] backend/app/services/llm_extractor.py:169-183,226-244,279-296,318 — first/last-brace
      slicing fails on any prose around the JSON (reproduced: a trailing "Note: …{schema}"), and
      is then reported as "Model unavailable"; `finish_reason == "length"` is unchecked, so a
      110-line order truncates identically on every retry; one bad field (`"w": "0,386"`)
      drops the whole line with only a warning; receipt text follows the instructions with no
      delimiter, so a price-bearing line that reads like an instruction reaches the model as
      one.
- [ ] backend/app/parsers/receipt_lines.py:13, backend/app/parsers/heuristic.py:22 —
      `.*säästö` skips products such as `OMENA SÄÄSTÖPAKKAUS 4,99`; weights need exactly three
      decimals, so `1,2 kg 2,00 €/kg` is dropped and the product keeps quantity 1.
- [ ] backend/app/telegram_bot/runner.py:56-58 — updates are acknowledged only by the next
      `getUpdates`, so a crash mid-batch redelivers them; the SHA-256 dedupe turns that into a
      "Receipt already uploaded" reply per file, not a double receipt.
- [ ] backend/Dockerfile:15,41-49, frontend/Dockerfile:6, no `.dockerignore` in either — the
      documented local build copies `.venv`, `data/receipts` (real receipt files) and `logs`
      into the backend image, and the host's Windows `node_modules` and stale `.next` over the
      frontend's fresh install; the backend image ships pytest, ruff and mypy.
- [ ] frontend/components/inventory/QuickAddSheet.tsx:56-59,158-168 — "Create new" is offered
      while the debounced search is still pending, and the category it then demands is ignored
      by the resolver (which reuses the existing product by name) while the location the sheet
      derived from that category is kept: milk filed under beverages lands in the pantry.
- [ ] frontend/components/inventory/InventoryItemCard.tsx:88-105, frontend/components/ui/BottomSheet.tsx:62
      — every card's actions are named "Consume" and "Edit" with the product name in a sibling,
      so a screen reader hears forty identical buttons; the sheet's initial focus lands on
      Close.
- [ ] frontend/components/inventory/InventoryList.tsx:95 — the empty-stock copy says "Scan a
      product to add it"; there is no product scanner in the MVP.
- [ ] frontend/components/inventory/ConsumptionSheet.tsx:65-67, frontend/components/ui/Toast.tsx:13-18,130
      — a failed consume is a five-second toast that two later successes push out of the
      three-slot stack; on an unattended display the item silently reappears at its old
      quantity.

## Design misjudgements
Foundational choices behind the defects above, with what they cost.

1. **The status machine has no owner.** `apply_quantity_status` handles consume and
   corrections, `update_inventory_item` handles discard by hand, nothing guards transitions out
   of `discarded` or `empty`, and `current ≤ initial` is enforced nowhere at write time. The
   invariants live only in threshold tests. Every new write path (agent consume-by-name, undo,
   clear-expired) re-derives the rules; one `transition(item, event)` with an explicit table
   would replace all three.
2. **Closed unions are trusted at render time and enforced nowhere.** `InventoryItemStatus`
   and `InventoryLocation` are closed in `types/`, the API accepts free strings, and components
   index maps by them; one place defends, one crashes. Normalise once at the API boundary
   (`normalizeInventoryItem` already exists) and render unknowns as their raw value.
3. **Sheets copy a list snapshot into local state, so there is no single source of truth while
   a sheet is open.** The stale-quantity overwrite is the first casualty; push updates
   (post-MVP item 1) will make it routine. Every sheet then needs its own "what changed since I
   opened" logic, or edits become lost-update races.
4. **Tests are coupled to the developer's real database and rebuild the ORM schema per test.**
   One wrong `.env` deletes local data; each DB test pays a schema rebuild; the schema under test
   is the ORM's, not the migrations' (CI covers that only because it runs `alembic upgrade head`
   first). A dedicated test database plus per-test transactions fixes all three.
5. **The fallback path is the least checked path.** The model boundary has one error class for
   transport failures, format failures, truncation and garbage, so the cook's only remedy is
   "Read again", which repeats every cause except a real outage. The heuristic parser is
   positional (modifiers attach to `products[-1]` regardless of what came between) and emits no
   confidence, so its wrong quantities look exactly like right ones.
6. **Quick add re-implements product identity in the UI.** The sheet decides existing-vs-new
   from a search result, demands a category on that basis, and derives location, unit and
   expiry from it, while the backend decides by name and ignores the category. This is the
   second place `docs/PRODUCT_RESOLUTION_SPEC.md` will have to change (synonyms mean "oat
   drink" may already be a product the search does not show).
7. **Category is half seed data, half user data.** Shelf life is a column copied to products at
   creation; storage is a code dict keyed by seeded ids; the API offers create, update and
   delete as if categories were user data. Cost: the `spices` scenario, the category-delete
   500 from the first report, and a PATCH on shelf life that changes nothing for existing
   products without saying so.
8. **Feedback is toast-only and time-boxed on a display nobody is watching, and the
   consumption log cannot reconstruct what happened.** `useToast` is the only channel every
   mutation uses (3 s success, 5 s error, three visible). `consumed_at` and
   `consumption_context` are never written, corrections are unlogged, discards log whatever
   was left, and re-activation is not logged. Silent rollbacks today; "consumption learning"
   and "analytics" (post-MVP 8) will find a counter, not a history. Decide the event vocabulary
   and a persistent status surface before either lands.

## Verified sound
- Every inventory read path eager-loads product and category (`_with_product`), including the
  post-commit reload after create, update, consume and quick add, so the model properties cannot
  raise; the list is three queries regardless of size, sorted with a total order on the indexed
  `expiry_date`.
- Unit conversion happens exactly once at the schema boundary and only for fields the client
  sent (`canonicalize_units` checks `model_fields_set`); PATCH carries no unit, so corrections
  cannot be double-converted; an unknown unit is a 422 before any DB work.
- Consumption options hold at the edges: 1 pcs offers only "All 1", 0.5 pcs only "All 0.5",
  2 dl left of 10 dl drops every fraction, large counts stay 1/2/3 plus All, a used-up item
  disables everything (`lib/consumption.ts:56-104`, tested).
- The frontend flow tests are real: consume, edit and quick-add flows run the actual hooks
  against msw handlers and assert request bodies, the optimistic list, rollback and toasts; only
  two component tests mock the hook, and the flows cover what they skip.
- `BottomSheet` traps Tab both ways, closes on Escape, restores focus, uses real dialog roles,
  and pads for the home indicator; `ChoiceGroup` is real radio inputs, so units, locations and
  categories work with keyboard and VoiceOver. PWA install is complete for iPadOS.
- Migrations: the chain is linear, the canonical-units data migration scales every table with a
  copied mapping and reports unknown units instead of guessing, the cascade change is scoped to
  consumption history, and CI runs `alembic upgrade head` on a fresh database before pytest.
- `images.yml` builds only on push to `main` with the repository-scoped token, tags `latest`
  plus the long SHA, and runs nothing for fork pull requests.
- Open Food Facts answers 200 with `status: 0` for an unknown barcode (checked live), so unknown
  codes are 404s, not 503s; the Telegram client never puts the token in an exception or log
  line.
