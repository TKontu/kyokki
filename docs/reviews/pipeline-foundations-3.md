# Pipeline Review: foundations, round 3 (the ground around the code)

Reviewed at 23b83ad (same tree as origin/main e233db5, 2026-09-17).

Scope: what the first four reports did not touch because it is not application code. Whether
the documentation, runbook, env examples and the CLAUDE.md command table still describe
reality (each safe command was run); the dependency and supply-chain posture, with untrusted
receipts in mind; the exposure of the unauthenticated API on the LAN; data at rest and
retention; repository hygiene; and whether the test suites are green and cover the paths the
earlier reports lean on (the frontend suite was run twice; the backend suite could not be run
on this workstation, see Critical #2). Gathered by three readers plus a core pass; every
headline claim was re-checked directly.

Earlier reports stand and are not repeated: `pipeline-receipt-processing.md`,
`pipeline-receipt-confirm.md`, `pipeline-foundations.md`, `pipeline-foundations-2.md`.

## Flow
Not a chain. Read and run: CLAUDE.md command table; docs/DEPLOY.md, docs/README.md,
docs/ARCHITECTURE.md as-built note, docs/SETUP_SUMMARY.md, docs/FRONTEND_PLAN.md,
docs/SCANNER_ARCHITECTURE.md, docs/TODO.md sprint block, HANDOFF.md; .claude/ profiles and
templates; backend/requirements.txt, frontend/package.json and lock, `npm audit --omit=dev`,
published advisories for the exact versions; api/router.py and every endpoint for the
blast-radius table; ocr_service.py, crud/receipt.py, main.py, websockets for input handling;
.gitignore, git history for env files; backend/tests/conftest.py, pytest.ini, the frontend
jest run and coverage.

## Critical (must fix)
- [ ] docs/DEPLOY.md:161,165 — **The Telegram deploy steps drop `--env-file stack.env`**, which
      every other compose command in the runbook passes (lines 74-81, 138-139). Compose loads
      only `.env`, never `stack.env`, so on a fresh homelab `POSTGRES_PASSWORD` is empty and the
      Postgres image refuses to start; on this workstation the legacy root `.env` is silently
      interpolated instead, with a different password from the running database. Line 161 also
      passes `--build` to a compose file with no `build:` sections.
- [ ] CLAUDE.md:22-33, backend/app/core/config.py:9,112, backend/tests/conftest.py (settings
      imported at collection) — **The documented backend commands cannot go green on the
      primary workstation.** `test-backend` and `test-one-backend` exit 4 before collecting any
      test, DB-free ones included, because conftest imports settings and the loader reads the
      repo-root `.env` with `extra="forbid"`; `typecheck` fails both ways (the system Python has
      no mypy; the venv's mypy exits 1 with the 149-error baseline). The Definition of Done
      ("tests passing, typecheck clean") is unattainable as written, and the only workaround
      lives in a private memory rather than the repo. Backend pass/fail and coverage are
      therefore unverified locally; CI is the sole evidence they are green.
- [ ] frontend/components/inventory/__tests__/QuickAddSheet.test.tsx:147 (and 175-276),
      frontend/hooks/__tests__/useDeleteInventoryItem.test.tsx:47-62 — **The frontend suite is
      flaky.** Run 1: 2 failed / 484 passed; run 2: 486 / 486. QuickAddSheet waits for a search
      result with the default 1 s `findBy` timeout across a 250 ms real debounce plus msw
      round-trips under a parallel run (13-20 s per file); the delete test saw one DELETE escape
      msw to the network (`AggregateError`). Every full run ends with "a worker process has
      failed to exit gracefully". Fix: fake timers around the debounce, a `findBy` timeout
      above debounce plus latency, and `--detectOpenHandles` to find the leak.

## Important (should fix)
- [ ] frontend/package.json:17 (`next` 14.2.35), package-lock.json — **The Next.js 14 line no
      longer receives security backports.** `npm audit --omit=dev` reports 1 critical and 2
      high; the only offered fix is `next@16.3.5`, a major. Advisories that apply to code paths
      this app has: App Router RSC deserialisation denial of service (GHSA-h25m-26qc-wcjf,
      GHSA-q4gf-8mx6-v5v3, GHSA-8h8q-6873-q5fj; precondition is `frontend/app/`, which exists),
      and request smuggling through rewrites (GHSA-ggv3-7p47-pfv8; precondition is a rewrite to
      an external backend, which `next.config.mjs:12-15` is). Any LAN device can make the
      frontend container spin or die, and the always-on iPad shows a dead page until a restart
      (no healthcheck). Checked and not applicable: the middleware bypass (no `middleware.ts`),
      the AVIF optimiser RCE (no `sharp`, no `next/image`), Server Action advisories (no
      `'use server'`). The upgrade grows every month it waits (React 19, caching and async
      request API changes).
- [ ] backend/requirements.txt (1 exact pin, 23 lower bounds), backend/Dockerfile:13, no lock
      file — **Production images resolve dependencies fresh on every push to main.** Today's
      resolve is patched for every advisory checked (pdfminer.six 20260107, python-multipart
      0.0.32, starlette 1.6.0, fastapi 0.141.1), but the precedent is exact: pdfminer.six before
      20251107 executed attacker code from a crafted PDF via pickle CMap loading
      (CVE-2025-64512, completed in 20251230), and this app feeds every PDF a phone shares
      straight into pdfminer in the worker (ocr_service.py:59-69). An image built in such a
      window ships with no diff in the repo. Pin with a lock (`pip-compile` or `uv lock`) and
      add `pip-audit` and `npm audit` to CI.
- [ ] backend/app/api/endpoints/websockets.py:12-28, backend/app/services/websockets.py:25,
      backend/app/api/endpoints/receipts.py:35-43 — **"LAN only" does not hold against a
      household browser on a malicious page.** CORS is explicit for JSON routes, but the
      WebSocket endpoint accepts with no `Origin` check, so any web page open on a LAN laptop
      can connect to `ws://<host>:17300/api/ws` and read every inventory and receipt broadcast;
      and the upload route takes `multipart/form-data`, which browsers send cross-origin
      without preflight, so the same page can post files to `/api/receipts/scan` (response
      unreadable, side effect real): disk fill, queue and GPU time. Check `Origin` on the
      WebSocket; require a custom header or origin allowlist on the upload route.
- [ ] backend/app/services/ocr_service.py:59-69, backend/app/api/endpoints/receipts.py:62 —
      **A large PDF ties up the only worker and then floods the model.** pdfplumber runs every
      page with no page, size or time cap; the API upload has no size cap (the bot caps at
      20 MB). A 300-page scanned catalogue shared by mistake grinds the worker thread for
      minutes, the API side marks it stale-failed at 10 min while the thread keeps running and
      later overwrites `completed`, and the extracted text is sent whole to the gateway, which
      truncates at 8192 tokens → "Model unavailable" → the heuristic parser produces hundreds of
      "products". A receipt is 1-3 pages; cap pages, bytes and thread time.
- [ ] docs/ARCHITECTURE.md:11-19, docs/DEPLOY.md:15-16, docs/README.md:12,81-84, CLAUDE.md:12,
      .claude/templates/profiles/*.md, docs/TODO.md:1024 — **The documents a new agent is told
      to read contradict the code and each other.** The as-built note says no alias lookup, no
      vision fallback, BackgroundTasks instead of Celery, DEC-1/2/4 still open; each is
      contradicted two bullets later or by the code (matching_service.py:124,
      receipt_processing.py:138-144, app/worker/, TODO.md:86-95). DEPLOY says uploads land in
      `./data`; the prod compose uses named volumes (line 45-47) and DEPLOY's own Operations
      section says so. README describes swipe-to-mark-gone, Clear Expired and breakfast
      context, none of which exist. The two style profiles describe a different codebase
      (`Depends`-injected services, Vitest, Zod). The sprint block still shows R6 and R8 as
      open PRs and never records #48-#50.
- [ ] backend/tests/services/test_receipt_queue.py:73-86, backend/tests/services/test_receipt_confirm.py:411,
      backend/app/schemas/receipt.py:75-133 — **The two database locks the earlier reports rely
      on are tested only sequentially**, and the legacy-blob tolerance that `items_from_structured`
      promises in its docstring has no test. No test contends `claim_next`'s SKIP LOCKED with a
      second session, none issues two overlapping confirms against the `FOR UPDATE`, so the
      confirm-versus-requeue race from the confirm report and the future multi-worker queue have
      no regression net. Two `AsyncSessionLocal()` contexts under `asyncio.gather` would cover
      both.
- [ ] git history (0509841 → ae235a7), HANDOFF.md open operator items — **The public
      repository's history still carries the compose env file that was tracked until MVP-F1**:
      a nine-character Postgres password (starts like a placeholder), the gateway key `ollama`,
      internal LAN addresses. The root `.env` was never tracked and no secret-shaped string is
      tracked today. The handoff lists "rotate Postgres password + LLM key, purge stack.env
      history" as still open; if the homelab still uses that password, rotation matters more
      than the purge.

## Minor
- [ ] .env.example, stack.env.example — `ALLOWED_ORIGINS`, `TELEGRAM_API_BASE` and
      `TELEGRAM_POLL_TIMEOUT` are settings with no example line (CLAUDE.md's Definition of Done
      asks for one).
- [ ] No `.gitattributes`; 329 tracked blobs carry CRLF. Diffs and `git blame` explode whenever
      an editor normalises a file (the CRLF memory exists because of this). Add
      `* text=auto eol=lf` and normalise once in its own commit.
- [ ] backend/app/crud/receipt.py:161-183, no `DELETE /receipts` route — receipt files, full
      OCR text (store, till, time, loyalty and payment lines) and structured lines are kept
      forever; a year of shopping is about a gigabyte of images on the one volume nothing backs
      up. Decide a retention rule (delete the file N days after confirm, keep the lines).
- [ ] backend/app/crud/receipt.py:102-103 — the stored suffix is the client's verbatim: an
      embedded NUL or a 10 000-character suffix is a 500 on upload. Deriving the suffix from
      the validated content type (the processing report's fix) closes this too.
- [ ] backend/app/main.py:43-46 — every Redis payload is logged at INFO; it is the only place
      household data (product names, quantities, receipt errors) enters the logs, which also
      have no retention.
- [ ] CLAUDE.md:70-74 rule violations on `main`: categories.py:4,42 catches `IntegrityError`
      inline instead of `handle_integrity_errors`; shopping.py:113,120,162 validates vocabularies
      in the router; products.py (4 mutating routes) and categories.py (3) broadcast nothing,
      and `_build_message` has no product or category message type, so the rule cannot be
      followed without new code. "Services never import from app.api" holds.
- [ ] backend/pytest.ini:28-35 — `requires_db`, `requires_redis`, `unit`, `integration`, `slow`
      are decorative: `requires_db` is on one file while about twenty depend on Postgres through
      the fixture, so `-m "not requires_db"` selects almost everything.
      tests/services/test_ocr_service.py:217 uses a bare `skip("Requires MinerU")` instead of
      `requires_mineru` and cites a `--run-mineru` flag that does not exist.
      tests/integration/test_connections.py:51-65 tests Ollama and a `qwen2vl` model the stack
      no longer uses; they are the "known 3 failing tests" that keep the CI integration job
      on `continue-on-error`.
- [ ] backend/tests/telegram_bot/test_runner.py:21,72, frontend/hooks/__tests__/useQuickAdd.test.tsx:67,
      useReceipts.test.tsx:89 — real-time sleeps (50 ms "not done", 400 × 5 ms poll, 300 and
      200 ms debounce waits); the same flakiness class as the Critical above.
      frontend/jest.config.js lists `stores/**` in `collectCoverageFrom`; no such directory.
      backend/tests/api/test_scanner.py:671 asserts 200 on `POST /scanner/mode` and nothing else.
- [ ] docs/SETUP_SUMMARY.md, docs/FRONTEND_PLAN.md, docs/SCANNER_ARCHITECTURE.md — a 2025 setup
      log naming files and hosts that no longer exist (`celery_app.py`, `kyokki_2/`, MinerU at
      `.136`, LLM at `.247:9003`), and two plans (Zustand, `next-pwa`, `useWebSocket`,
      `useOffline`) with no date, status or supersede banner. docs/README.md:58-60 still tells
      the operator to run migrations and the seed by hand after `up`; `kyokki-migrate` does
      both. docs/DEPLOY.md:60-61 says "healthy" for a body of `{"status":"ok"}` and "five
      services" for six.
- [ ] CLAUDE.md:52-57 — the layout block names `ws` (file is `websockets.py`), "store receipt
      parsers" (one generic heuristic parser exists), and "per-model data access on top of
      `crud/base.py`" (one user, shopping).

## Blast radius of the published API port (no auth, `API_PORT=17300` on the LAN)

| Route | Effect from any device on the Wi-Fi |
| --- | --- |
| `DELETE /api/inventory/{id}` | Deletes stock and its consumption history |
| `PATCH /api/inventory/{id}`, `POST …/consume` | Discards, rewrites quantity, expiry, location; reduces stock |
| `POST /api/inventory`, `/quick-add` | Creates stock and products |
| `DELETE /api/products/{id}`, `PATCH` | Deletes (or 500s) and renames products, changes shelf life and unit |
| `POST /api/products/enrich` | Creates products from Open Food Facts data |
| `POST /PATCH /DELETE /api/categories` | Rewrites or deletes seed shelf-life defaults |
| `POST /api/receipts/scan` | Writes files to disk, queues OCR and GPU work; postable cross-origin |
| `POST /api/receipts/{id}/process`, `/confirm` | Re-queues GPU work; creates stock, products, aliases, non-food memory |
| `DELETE /api/shopping/{id}`, `/purchased/all` | Deletes shopping rows |
| `POST /api/scanner/mode`, `/scan` | Flips a station between add and consume; adds or consumes stock |
| `GET /api/ws` | Streams every mutation to any origin |
| `GET /api/receipts/{id}` | Full OCR text and the server file path |

Every mutating route is one `curl` away; the one read that exposes household data beyond the
stock list is the receipt detail.

## Data at rest

| Data | Where | Logged | Deleted |
| --- | --- | --- | --- |
| Receipt files (PDF, JPEG) | `kyokki_data`, `data/receipts/<uuid>.<ext>` | filename only | never |
| Full receipt text: store, till, time, loyalty, payment lines | `receipt.ocr_raw_text`, returned by `GET /receipts/{id}` | no | never |
| Extracted lines and matches | `receipt.ocr_structured` | no | never |
| Stock, products, history, aliases, non-food names | Postgres | names and quantities via the Redis-listener log line | with the item |
| Telegram chat ids, bot token | Portainer stack env (git-ignored) | count only; token never | n/a |
| Postgres password, gateway key | stack env | printed by the settings error on a bad env (first report) | n/a |

## Design misjudgements
Foundational choices behind the defects above, with what they cost.

1. **Three documents claim to be the source of truth for what is built**, and each is edited by
   a different command at a different time: the ARCHITECTURE as-built note (contradicts
   itself), the TODO sprint block (lags a wave), HANDOFF (right). `/takeoff` reads the backlog as
   canonical while the architecture doc every agent is told to read says DEC-1 is still open.
   Plans (SETUP_SUMMARY, FRONTEND_PLAN, SCANNER_ARCHITECTURE, the target topology) never
   retire, so plan and record can only be told apart by diffing against code. One document
   should own status; the others link to it; plans get a status banner or a deletion.
2. **CLAUDE.md states rules as absolutes without a checker.** "Every mutating endpoint
   broadcasts", "endpoints never touch SQLAlchemy", "typecheck clean" are each violated on
   `main` today and nothing in CI or the hooks tests them. Rules that are not true read as
   aspirational, and reviewers stop citing them. A grep-based check per rule in CI, or wording
   that matches reality, fixes either direction.
3. **The command table assumes an environment the repo does not provide.** `python -m` on the
   system interpreter (no mypy), a settings loader that reads a repo-root `.env` (`config.py:9`)
   the project's own examples describe differently, and settings imported at test collection so
   one bad env file makes the whole suite uncollectable. Pin the interpreter in the table
   (`backend/.venv` or `uv run`), move `ENV_FILE` to `backend/.env`, and import settings lazily
   in conftest.
4. **Dependency versions are floors, not a set.** Backend `>=` everywhere with no lock, frontend
   `^` on React and react-query; only Next and ruff are exact. There is no reproducible build,
   no way to say what was running when a receipt was misread, and no audit step, so a
   compromised or vulnerable release lands in production on the next merge with nothing to
   review.
5. **The security boundary is the LAN, but the code relies on the browser's same-origin
   policy.** DEC-3's rewrite was chosen to avoid CORS and a baked LAN IP, not as a control, yet
   it is the only thing between a household browser and the API; the API port is also
   published directly, and neither WebSocket origin nor multipart uploads are covered by that
   policy. Every future write route needs its own "is preflight protecting this?" check. One
   shared secret header now, or Traefik forward-auth later, is cheaper than reasoning per route.
6. **Untrusted documents are parsed inside the process that owns the queue**, with no page,
   size or time caps: pdfminer (a pickle-loading pure-Python parser with a recent RCE) and the
   MinerU and model round-trips all run in the single worker. One bad PDF stalls every receipt
   behind it, and in the pickle scenario runs code with the worker's database credentials. A
   subprocess with a timeout and a page cap isolates both.
7. **Nothing is ever forgotten.** Files, OCR text, logs and broadcast payloads accumulate with
   no retention, no backup and no deletion route; the volume that grows forever is the one
   holding the most personal data, and the first "delete my receipt" request has no code path.
8. **The test suite discovers its needs at fixture time instead of declaring them**, mixes
   fake and real timers on debounced UI, and asserts concurrency invariants in comments. There
   is no way to run "just the unit tests", every DB test rebuilds the schema, the only red tests
   in the repo are timing races, and the two database locks have no regression net.

## Verified sound
- DEPLOY.md ports, service names, migrate-before-start ordering, the `sha-<commit>` rollback
  tags and the `run --rm kyokki-api alembic` guidance match `docker-compose.prod.yml`,
  `images.yml` and `.env.example`; the iPadOS 15 floor and the plain-HTTP limit are stated
  honestly. The env examples carry the same defaults as `config.py`.
- Every PR number cited in docs/TODO.md exists in `git log main`; HANDOFF.md is current and its
  mypy baseline of 149 reproduces exactly. `lint`, `format --check` and `test-one-frontend` pass
  from the repo root as documented.
- No secret-shaped string is tracked; the root `.env` and `backend/.env` were never committed;
  `.gitignore` covers env files, `data/`, `logs/` and `samples/`.
- Telegram messages are sent without `parse_mode`, so a printed name cannot break or inject
  formatting; the frontend has no `dangerouslySetInnerHTML` or `innerHTML`, so OCR text and
  model output are escaped; CORS is an explicit list with no wildcard; stored upload names are
  fresh UUIDs, so a filename cannot escape `data/receipts/`.
- Every installed backend version is current for every advisory checked (pdfminer.six
  20260107, python-multipart 0.0.32, starlette 1.6.0, fastapi 0.141.1, httpx 0.28.1, redis 8.1.0,
  SQLAlchemy 2.0.52, asyncpg 0.31.0, RapidFuzz 3.14.6).
- Every load-bearing rule from the Q-work has a direct test (fill-gaps never overwriting, g to
  pcs storage, the opened clock's piece-weight guard, the full status parametrisation, non-food
  remembered versus merely skipped); the worker's failure paths are tested at the boundary; the
  frontend flow tests run real hooks against msw with 89.6 % statement coverage and no
  snapshots.
