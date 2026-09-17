# Pipeline Review: foundations (whole system)

Reviewed at 23b83ad (same tree as origin/main e233db5, 2026-09-17).

Scope: not one lane but the ground the lanes stand on. The two lane reviews
(`pipeline-receipt-processing.md`, `pipeline-receipt-confirm.md`) are not repeated here; this
report covers the data model and its delete rules, product identity and the learning loop,
the matching foundation, the non-receipt write paths (consume, edit, quick add, scanner),
dates and numbers across the API boundary, the frontend data-flow design, configuration and
security posture, CI and type-checking, and the deployed topology. Findings were gathered by
three readers (core, backend breadth, frontend) and cross-checked; the substring over-match
and the settings failure were reproduced against the real code.

## Flow
Not a single chain. Surfaces read: api/endpoints/* → services/* → crud/* → models/* and
alembic/versions/*; worker and telegram_bot; core/config.py and core/logging.py; frontend
lib/api/client.ts → hooks/* → components/inventory/*, components/receipts/*, lib/consumption.ts,
lib/dates.ts, types/*; .github/workflows/*, docker-compose.prod.yml, backend/Dockerfile.

## Critical (must fix)
- [ ] backend/app/api/endpoints/products.py:91-99, backend/app/crud/product_master.py:128-144,
      backend/alembic/versions/c943e915cf61 (lines 129-133, 219, 267) — **Deleting a product
      with any history is a 500.** `inventory_item`, `store_product_alias`, `shopping_list_item`
      and `consumption_log` all reference `product_master.id` with no `ondelete`, and the
      endpoint is not wrapped in `handle_integrity_errors`. Any product that has been on a
      receipt has an alias row, so the delete fails for exactly the products anyone would want
      to delete. docs/TODO.md:845,886 names "delete the product" as the escape hatch for a
      wrong piece weight; that hatch does not work.
- [ ] backend/app/api/endpoints/categories.py:65-73 — same shape: `product_master.category` has
      no delete rule, so deleting any category that has a product is a 500. The passing test
      deletes `snacks`, which has none. Categories are seed data hard-coded in
      services/storage.py:326-339; they should not be deletable through the API at all.
- [ ] backend/app/services/off_service.py:117,128,154 vs backend/app/db/seed_categories.py —
      the Open Food Facts mapper returns `seafood`, `bakery` and `grains`; the seed has `fish`,
      `bread` and `pantry`. Scanning a salmon, bread or pasta barcode in add mode inserts a
      product with an unknown category, the FK violation is not caught by scanner.py:120-139
      (only OFF errors and `ValueError` are), and the request is a 500. No frontend calls this
      surface today; see misjudgement 7.

## Important (should fix)
- [ ] backend/app/services/matching_service.py:153-178,
      backend/app/services/receipt_confirm.py:118-160,
      frontend/components/receipts/ReceiptItemRow.tsx:82-90 — **The matcher over-matches by
      substring, the review screen cannot undo a match, and confirm turns it into a verified
      alias.** RapidFuzz `WRatio` scores a name against any catalog name it contains at 90.
      Reproduced with the real `MatchingService` and a catalog of Milk, Apple, Cream, Butter and
      Tomato: the model's correct answers Oat milk, Pineapple, Sour cream, Peanut butter and
      Cherry tomato all pre-select the wrong product at 90 "high" (threshold 80). A matched
      line is read-only on the review page (include or skip only), so the cook's only way to
      avoid the wrong product is to skip the line. Including it writes
      `store_product_alias(manually_verified=True)` and stocks pineapple as apples with the
      apple's piece weight; from then on the alias wins outright for that printed name. Fix:
      exact or token-complete matching for generic names (the generic name is already the
      model's normalised answer; fuzzy belongs to printed names only), a "not this product"
      control on the row, and learn aliases only from lines the cook confirmed or corrected.
- [ ] backend/app/crud/inventory_item.py:255-294,159-207 — **Consume and correction are
      read-modify-write with no lock.** Two overlapping consumes of one item (iPad and a phone,
      or the agent track later) both read 4 and both write 3; one consumption is lost while both
      `consumption_log` rows land. Fix: `SELECT … FOR UPDATE` on the write paths, or a
      conditional `UPDATE … SET current_quantity = current_quantity - :q WHERE
      current_quantity >= :q RETURNING`.
- [ ] .github/workflows/backend-ci.yml:64,229-245 — **The required check ignores lint and type
      failures.** `all-checks-pass` exits non-zero only when the test job fails; ruff and mypy
      failures print a warning and the PR merges green. CLAUDE.md's Definition of Done says lint
      and typecheck are clean and CI enforces it. Frontend CI does gate on lint.
- [ ] backend/app/core/config.py:112 — **Settings refuse unknown keys and echo their values.**
      pydantic-settings defaults to `extra="forbid"`, and the validation error prints every
      extra key with its full value. Reproduced: starting any backend process with the legacy
      root `.env` in place aborts and prints an API key, a database password and a connection
      string to the terminal or container log. Set `extra="ignore"`, and rotate what has been
      printed.
- [ ] frontend/app/receipt/[id]/page.tsx:276, frontend/components/receipts/ReceiptsBanner.tsx:28
      — **A receipt with nothing to add cannot be dismissed.** The confirm button is disabled at
      zero included lines, and the banner counts every `completed` receipt as waiting. An
      all-household receipt, a duplicate scan of stock already added, or a zero-item receipt
      from the processing review nags on the home screen indefinitely, and because confirm is
      never sent the household names are never remembered: Q1's memory never fires for the
      case it was built for. The backend already accepts an empty confirm.
- [ ] backend/app/services/scanner_service.py:233-235, backend/app/services/off_service.py:219-232
      — scanned `quantity` is ignored whenever the OFF product has a pack size, and OFF products
      are created as brand + name + pack outside `ProductResolver`, so the first barcode scan of
      a milk carton creates a second "milk" beside the receipt-created "Milk". Post-MVP surface,
      but reachable now, and its rules contradict the generic-product ruling.

## Minor
- [ ] backend/app/crud/inventory_item.py:63,151, backend/app/services/quick_add.py:43,
      frontend/components/inventory/QuickAddSheet.tsx:75-113, frontend/lib/consumption.ts:106,
      frontend/lib/dates.ts:39 — "today" is computed on two clocks with no timezone in the
      contract: the container is UTC (no `TZ` in docker-compose.prod.yml), the iPad is
      Helsinki. Between 00:00 and 03:00 local, `opened_date`, the quick-add purchase date and
      the `expiring_days` filter are a day early; the expiry badge parses `YYYY-MM-DD` as UTC
      midnight then zeroes local hours, which is one day off anywhere west of UTC.
- [ ] backend/app/crud/inventory_item.py:195-204, backend/app/services/storage.py — expiry is a
      function of the product only; moving an item to the freezer through the edit sheet keeps
      the fridge shelf life, so mince frozen on day one reads "expired" on day six.
- [ ] backend/app/services/broadcast_helpers.py:20-27 — the Redis client has no socket or
      connect timeout. Broadcasts run after commit, so a Redis that accepts TCP but stalls
      blocks every mutating request with the data already written; with `retry: false` the
      client sees only a timeout.
- [ ] backend/app/schemas/inventory_item.py:20-34 and every model — `status`, `expiry_source`,
      `location`, shopping `priority` and `source` are free strings validated in some endpoints
      and not others; `POST /inventory` with `status: "gone"` is stored and never hidden by the
      inactive filter. Receipt status is the one `StrEnum`.
- [ ] frontend/lib/api/client.ts:115-123, ConsumptionSheet.tsx:60, ItemEditSheet.tsx:34,
      QuickAddSheet.tsx:123, receipt/[id]/page.tsx:194 — any non-`APIError` throw is reported
      as a network failure, and every 4xx body is shown verbatim, including pydantic 422 text
      and asyncpg detail strings from `handle_integrity_errors`.
- [ ] frontend/app/ — no `error.tsx` or `global-error.tsx`; on the always-on iPad a render-time
      throw replaces the app with Next's error screen until someone reloads it by hand.
- [ ] frontend/types/product.ts, frontend/types/inventory.ts:80-87 — `avg_piece_grams` is
      missing from the product type (the field the product editor needs); `InventoryListParams`
      carries `context` and `category`, which `GET /inventory` does not accept and drops.
- [ ] backend/app/telegram_bot/messages.py:52-56 — `failure_text` forwards `receipt.error`
      verbatim, so a gateway outage puts the internal gateway URL and `ConnectError(...)` into
      the chat.
- [ ] backend/app/main.py:43-46, backend/app/core/logging.py — every Redis message is logged at
      INFO with its payload and access logs share the 10 MB × 5 rotating file; with the iPad
      polling every 3 s during a read, the R4 timing lines rotate away within days.
- [ ] docker-compose.prod.yml:66-83,123-133, backend/Dockerfile, stack.env.example:16-17 — no
      healthcheck on the API (the frontend proxies 502s after each deploy), the backend runs as
      root, nothing backs up `kyokki_data` (the receipt files), and `API_PORT` publishes the
      unauthenticated API on the LAN beside the same-origin proxy that DEC-3 introduced to avoid
      exactly that.
- [ ] frontend/hooks/useInventory.ts:62 — `useCreateInventoryItem` is unused and keeps the
      default retry on a non-idempotent POST.

## Design misjudgements
Foundational choices that are producing the defects above, with what they cost.

1. **Product identity is a model-chosen string, and the learning loop trusts it.** A product is
   `lower(canonical_name)` with no unique constraint, no synonyms and no merge; matching adds a
   substring-tolerant fuzzy step on top; confirm writes verified aliases from lines the cook
   only had the option to skip. Together these make the system's memory a faithful record of
   its own mistakes: naming drift ("Minced beef" vs "Ground beef", WRatio 64, so two products)
   splits stock, substring matches merge distinct products, and neither is correctable from the
   UI. The prompt's 300-name catalog list is a second, weaker copy of the same mechanism and
   grows with the catalog (the three Q-fields already cost about 27 % more model time).
2. **The first guess is permanent.** Piece weight, shelf life and opened shelf life come from
   the model's priors at first sight; `_fill_gaps` never overwrites; there is no product editor;
   delete is a 500. A product's facts can only ever be set once, by a model that the handoff
   records wavering, and never by the cook.
3. **Receipt lines have no identity.** Extracted lines are a JSONB array on the receipt and are
   addressed by position everywhere: review rows, edits, `ConfirmedItemCreate.index`,
   `non_food_indexes`, alias learning. A re-read renumbers everything silently (the stale-edits
   finding in the confirm review), and nothing records what the cook changed on a line, so the
   wavering the Q-work exists to fix cannot be measured. A `receipt_line` table, or stable ids
   in the blob, is the missing primitive.
4. **Type checking has been switched off where the state machines live.** Models use legacy
   `Column()` rather than `Mapped[]`, so 67 of the 149 baseline mypy errors are `Column[X]` vs
   `X`, and the code answers with `row: Any = item` casts in receipt_confirm, receipt_queue,
   non_food and crud/inventory_item, which is precisely the status and quantity logic. mypy is
   `continue-on-error`, the CI gate ignores it and lint alike, and real type errors already sit
   in the baseline (receipt_processing.py:194,270 pass a `ReceiptStatus` where a `Literal` is
   declared; categories.py:18 returns ORM rows as a response model). Moving to `Mapped[]` is
   mechanical, would take the baseline near zero, and would let the gate become real.
5. **No delete semantics in the data model.** No FK except `consumption_log → inventory_item`
   has an `ondelete`, yet DELETE endpoints exist for products and categories. Decide per FK
   (RESTRICT with a 409 that names the references, soft delete, or merge) before the product
   editor lands, because the editor's first request will be "get rid of this product".
6. **Business rules are implemented twice.** `lib/consumption.ts` mirrors the status thresholds,
   rounding, opened date and the consumption ladder so the optimistic cache can predict the
   server, and has already diverged (it skips the opened clock). The refetch papers over any
   disagreement within a second, so drift stays invisible until it is not.
7. **Two product-creation paths, one of them unused.** `ProductResolver` (generic, English,
   category-derived storage) versus the scanner/OFF path (brand + pack, keyword categories that
   do not exist, a 365-day fallback). The scanner surface is about 700 lines with no frontend
   caller and is explicitly post-MVP; it is kept green by tests and keeps shipping bugs nobody
   hits. Route it through the resolver or quarantine it behind a flag and stop maintaining it.
8. **Dates have no owner, and broadcasts have no consumer.** The browser computes display
   dates in local time, the server stores them in UTC, and no timezone travels in the contract;
   every date-bearing feature (opened tracking, consumption learning, analytics) inherits the
   split. Meanwhile CLAUDE.md requires every mutation to broadcast over Redis while the PWA has
   no WebSocket client and polls instead, each list poll costing a write transaction. Both are
   sequencing choices rather than mistakes, but both are now load-bearing rules that cost more
   than they deliver.

## Verified sound
- Each uvicorn worker runs its own Redis listener and connection manager (main.py:70-85), so a
  WebSocket client on either worker sees every published message.
- `kyokki-migrate` runs `upgrade head` plus the idempotent seed before api, worker and bot start
  (`service_completed_successfully`), and CI runs `alembic check`, so a deploy cannot start on
  an old schema.
- Telegram: the chat allowlist is checked before any file metadata is read or downloaded; the
  token is a `SecretStr`, HTTP client loggers are quieted, and `TelegramError` is rebuilt from
  the method name, so the token never reaches a log line; poll failures back off to 60 s.
- `apply_quantity_status` is the single status rule for consume and corrections; the opened
  clock only ever moves expiry earlier and skips loose produce by piece weight; consumption log
  rows land in the same transaction and cascade with the item.
- Non-idempotent mutations on the frontend set `retry: false`; optimistic consume cancels
  in-flight refetches, snapshots every cached list, rolls back on error and reconciles on
  settle; the home page and the list share one query key.
- DEC-2 and DEC-3 hold end to end: decimals travel as JSON numbers and are coerced and rounded
  to 2 dp on both sides; the client bundle contains no LAN IP or CORS origin.
- DB-backed tests fail rather than skip in CI (`KYOKKI_TEST_REQUIRE_DB=1`); the local skip is
  deliberate and documented.
