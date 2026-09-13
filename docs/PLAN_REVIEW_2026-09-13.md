# Architecture and MVP Plan Review — 2026-09-13

> Status: the amendments in sections 6 and 8 were applied to `docs/TODO.md`,
> `docs/ARCHITECTURE.md`, the area TODOs and `docs/vLLM_MANUAL_TEST.md` on 2026-09-13.
> The four operator decisions in section 7 are tracked as DEC-1…4 in `docs/TODO.md`.

Scope: `docs/ARCHITECTURE.md`, the MVP increment plan in `docs/TODO.md` (MVP-F1 … MVP-P3),
`docs/FRONTEND_PLAN.md`, and the code the plan builds on (`backend/app/**`, `frontend/**`,
both compose files, CI). Every claim below was checked against the source on branch
`fix/mvp-f1-green-ci-secrets` at base `6382f34`; nothing is taken from the README or handoffs.

Verdict in one paragraph: the MVP scope is right, the wave structure is sound, and the
decisions to use polling instead of WebSockets, FastAPI `BackgroundTasks` instead of Celery,
and a file input instead of `getUserMedia` are all correct. The plan has one critical
sequencing error (the only unproven component, LLM extraction, is validated in Wave 3 after
roughly 30 hours of dependent work), one critical architectural gap (nothing in the plan makes
receipt matching improve with use, so the review screen stays a per-line chore forever), and a
handful of verified code-vs-plan mismatches that will surface as bugs during R1, R2, C2 and F2
unless the increments are amended. Recommended amendments are collected in section 6.

---

## 1. Critical

### C1. The riskiest unknown is scheduled last-but-one

`docs/vLLM_MANUAL_TEST.md` records that a real S-kaupat receipt (about 60 lines, 40 products)
never completes: the model loops for over 300 s and fills the KV cache. Only the three-line
toy receipt has ever been extracted successfully. `llm_extractor.py` still sends
`max_tokens: 16384` with a 300 s timeout and no thinking control, so the failure is current.

The plan puts the fix in MVP-R4 (Wave 3, after F1, F2, R1, and in parallel with R3), and
makes R6/R7 (Wave 4, ~18 h) conditional on it only through "if this cannot be met, stop and
file a DEC". By then S1, R1, R2, R3, C1, C2 (~30 h) are built on the assumption that the
pipeline works.

R4 does not need any of that work. It needs the homelab LLM endpoint, the receipt text in
`vLLM_MANUAL_TEST.md`, and `curl`. Move the feasibility part of R4 into Wave 1 as a
time-boxed spike (2 h) and keep the "five real receipts through the deployed stack" part
where it is. The spike should try, in this order:

1. `chat_template_kwargs: {"enable_thinking": false}` in the request body (vLLM's switch for
   Qwen3 hybrid-thinking models), or a `/no_think` suffix in the prompt. The note in the code
   that `response_format` "causes thinking loops" describes thinking mode interacting with
   guided decoding, not a problem with guided decoding itself; retry `response_format` with
   `json_schema` once thinking is off.
2. `max_tokens` capped at 4096. A 40-product receipt in the current schema is about 2500
   output tokens; 16384 only gives a looping model more rope.
3. Cut the prompt to what the MVP uses. `name_en`, `country`, `language`, `currency`,
   `confidence` and `price` are requested and stored but nothing reads them. Fewer output
   tokens per line is the cheapest latency win available.
4. Deterministic pre-filtering of the OCR text before it reaches the LLM. The skip patterns in
   the ARCHITECTURE.md appendix (`YHTEENSÄ`, `ALV`, `Kortti:`, `Viite:`, `TOIMITUSMAKSU`,
   `NORM.`, `ALENNUS`, the VAT table, card details) remove a third of the real receipt and
   remove the need for the "skip totals" instructions in the prompt.
5. If a single call still cannot finish, chunk product lines into batches of ~15 and merge.
   Bounded output per call; batches can run concurrently.

If none of these gets five receipts under 120 s, the DEC should be filed in Wave 1, not Wave 3,
and the fallback in C2 below becomes the primary path.

### C2. Matching has no memory, so review friction never decreases

`matching_service.py` matches receipt names only against `product_master.canonical_name`
with RapidFuzz. `store_product_alias` exists in the schema and model (`receipt_name`,
`store_chain`, `manually_verified`, `occurrence_count`) but is never read or written
anywhere in `app/`. The design principle "Learns from corrections" has no implementation
and no increment in the plan.

Consequences under the current plan:

- The product table starts empty. The first receipt produces 30 to 40 "new product" rows on
  the review screen, each needing a category choice. That is expected once.
- R2 auto-creates products with `canonical_name = name`, the receipt's abbreviated all-caps
  string (`MANGO KEITT/KENT/OSTEEN`, `KEVYTMAITOJUOMA LAKTON`). That is what the iPad
  stock view will display. The user will rename them.
- Once renamed, the next receipt's fuzzy match against the nice name is unreliable
  (`MANGO KEITT/KENT/OSTEEN` versus `Mango`), so the same line is "new" again and the user
  re-does the work. The second receipt is nearly as much work as the first.

Fix, small enough to fold into R1 and R2:

- **R2 confirm** writes one `store_product_alias` row per confirmed item: `receipt_name` =
  the extracted name, `store_chain` = the receipt's chain or `unknown`, `product_master_id`
  = the chosen or created product, `manually_verified = true`, `occurrence_count += 1` on
  repeat.
- **R1 matching** checks aliases first: normalised exact match on `receipt_name` (optionally
  scoped to `store_chain`) returns the product with confidence `exact`; only unmatched names
  fall through to RapidFuzz. Aliases should also be included as candidate strings in the fuzzy
  pass, so the OCR-noise variant of a known line still lands on the right product.
- **R7** does not change. The benefit is that after two or three receipts, most rows arrive
  pre-matched and the user only touches genuinely new products.

This is the single change with the best value-to-effort ratio in the whole plan. Without it
acceptance item 7 (five receipts end to end) is achievable, but acceptance week (P3) will
show the receipt flow as too much work to keep using.

### C3. Quantities are JSON strings on the wire; the frontend assumes numbers

Verified with the backend venv (pydantic 2.9.2): a `Decimal` field serialises as
`"750.00"`, not `750`. `InventoryItemResponse.current_quantity` and `initial_quantity` are
`Decimal`. `frontend/types/inventory.ts` declares them `number`, and every frontend test
fixture uses numbers (`current_quantity: 750`). ARCHITECTURE.md section 9.5 even shows the
string form in its WebSocket example.

JavaScript arithmetic coerces (`"1000.00" * 0.25` is `250`), so C2's fraction maths will
look right in msw-backed tests and mostly work in the browser, but `===` comparisons, string
concatenation in labels, `toFixed`, and `Intl.NumberFormat` will not. Tests written against
numeric fixtures cannot catch it.

Fix in **S1**, which already changes `InventoryItemResponse`: add a `field_serializer` (or
`PlainSerializer` annotation) that emits `float` for the quantity fields, and add one backend
test that asserts the JSON type. Do the same for `ProductMasterResponse.default_quantity`.
Alternatively change the TS types to `string` and parse at the API boundary; either is fine,
but decide before C2 is written.

---

## 2. Significant

### S1. The Celery worker container crash-loops in both compose files

`app/core/celery_app.py` has `include=["app.tasks"]`; `app/tasks` does not exist. The
worker container fails at import, and `docker-compose.prod.yml` restarts it forever
(`restart: unless-stopped`). MVP-R3 says the worker "can be removed from compose or left
idle"; it cannot be left idle. Remove the `celery-worker` service from both compose files,
delete `celery_app.py`, and drop `celery` from `requirements.txt` in **F2**, where the compose
file is already being edited. The ARCHITECTURE.md queue row should say "none (in-process
background task)".

### S2. Background processing needs stale-state recovery and a timeout

MVP-R3 runs the pipeline in `BackgroundTasks` and returns 409 while `processing`. Two gaps:

- `MINERU_TIMEOUT` defaults to `None` (no timeout) and the LLM timeout is 300 s. A hung OCR
  call leaves a receipt in `processing` indefinitely, and the 409 rule then makes it
  impossible to retry. Set a real default (120 s) for MinerU.
- A container restart (deploy, crash, `--workers 2` recycle) loses every in-flight task with
  the row still saying `processing`.

Add `processing_started_at` to the receipt (R3 already needs a migration for `error`, see
S6) and treat `processing` older than 10 minutes as `failed` on read and on `/process`. Let
`/process` re-run `failed` receipts. Also note that with `--workers 2` the task runs in
whichever worker took the request; that is fine for MVP but worth a comment in the runbook.

### S3. Confirm puts everything in the fridge

`confirm_receipt` hardcodes `location="main_fridge"`, and R2 keeps `location: str =
"main_fridge"` as the default. Rice, flour, coffee, canned tomatoes and frozen peas from a
Prisma receipt will all appear under "Fridge" in S2's location groups, and the user has to
move each one by hand (S4). Acceptance item 1 ("grouped by location") is technically met and
practically wrong.

Derive the default from the category in R2: `frozen → freezer`; `pantry`, `condiments`,
`snacks`, `beverages` → `pantry`; everything else → `main_fridge`. Send it as the pre-filled
`location` in the R1 `ExtractedItem` so R7 shows it and the user can change it before
confirm. The same mapping gives `ProductMaster.storage_type`, which is `nullable=False` and
which R2's text does not say how to fill.

### S4. Three different unit vocabularies

- LLM output and `ParsedProduct.unit`: `pcs | kg | l | unit`, plus `weight_kg` and
  `volume_l` fields.
- Backend inventory: free `str`, seeded by the receipt value.
- Frontend `types/inventory.ts`: `Unit = 'ml' | 'g' | 'pcs' | 'unit'`.

A confirmed weighed item arrives as `0.386 kg`; the frontend type forbids `kg`. C2's
acceptance example ("¼ of 1000 ml = 250 ml") assumes ml, which the receipt path never
produces. Decide one canonical set before R1: recommended `ml | g | pcs`, with R1
normalising `kg → g × 1000`, `l → ml × 1000`, and `unit → pcs`. Put the mapping in one
backend function and one test; update the TS type to match.

### S5. Same-origin proxy instead of CORS plus a baked API URL

F2 plans to parametrise `NEXT_PUBLIC_API_URL` with `${KYOKKI_HOST}` and document
`ALLOWED_ORIGINS`. That keeps three things coupled to the LAN IP: a build-time argument
(changing the IP means rebuilding the frontend image), the CORS list, and every future TLS
step (two origins to certify).

Alternative: add a Next.js rewrite `'/api/:path*' → 'http://kyokki-api:8000/api/:path*'`.
The destination is the compose service name, which never changes, so build-time evaluation
of `next.config.mjs` is not a problem. The browser then talks only to
`http://<host>:17301`; CORS configuration becomes unnecessary, `NEXT_PUBLIC_API_URL`
defaults to `/api`, `stack.env` loses two variables, and the runbook loses a paragraph. Next
rewrites do not proxy WebSockets, which is fine for MVP (polling); when WebSockets return
post-MVP, a Caddy or Traefik front will carry both anyway.

### S6. Model and migration drift; the runbook will silently deploy the wrong schema

There is one Alembic revision. PR #21 added `UniqueConstraint("off_product_id")` to the
model with no migration, so `alembic upgrade head` on the homelab produces a schema without
it while tests (which use `create_all`) pass. R1, R2 and R3 all need columns (`error`,
`processing_started_at`, possibly a per-item match table). Add to **F2**'s acceptance: a CI
step that runs `alembic check` (or `alembic revision --autogenerate` and fails on a
non-empty diff) so drift is caught, and a migration that adds the missing constraint.

### S7. OCR is told the receipts are English

`ocr_service.py` sends `lang_list: "en"` to MinerU. Receipts are Finnish with `ä`, `ö`,
`å`. Depending on the MinerU pipeline this can degrade recognition of exactly the
characters that distinguish products. Make it a setting (`MINERU_LANG`, default `fi`) and
include "OCR language" as a variable in R4's measurements. Also send the actual content type
rather than a hardcoded `image/jpeg`.

### S8. iPad camera photos are large

An iPad camera capture is 12 megapixels and 3 to 5 MB. Upload over LAN is fine; MinerU
time and LLM prompt length are not, and `llm_extractor.py` already truncates OCR text to
4000 characters, which a long receipt with headers exceeds. R6 should downscale on the client
(canvas, long edge 1600 to 2000 px, JPEG quality 0.85) before upload. Cheap, and it makes
the R4 timings representative of what the iPad will send.

### S9. Consumption is not logged

`consume_inventory_item` in `crud/inventory_item.py` mutates the item and never writes
`consumption_log`; nothing in `app/` writes that table. "Mark as gone" (S4) and "discard"
likewise. P3's acceptance week will therefore generate no data for waste tracking, the
"learns consumption patterns" features, or even a simple "what did we throw away" answer.
Writing one row on consume and on discard is about twenty lines and one test. Add it to S1
(the only backend inventory increment in the plan) so P3 produces usable history.

### S10. Postgres and Redis are published to the LAN in production

`docker-compose.prod.yml` publishes `17302:5432` and `17303:6379`. Redis has no
authentication and Postgres uses the password that F1 is rotating because it was exposed.
Neither needs a host port; the API reaches them over the compose network. Remove the port
mappings in F2, or bind them to `127.0.0.1` if psql access from the host is wanted.

### S11. Status enums diverge

`Receipt.processing_status` is documented as `queued | processing | completed | failed`, the
model defaults to `queued`, `create_receipt` writes `uploaded`, `confirm` writes
`confirmed`, and `frontend/types/receipt.ts` knows neither `uploaded` nor `confirmed`. R1
should define the enum once in `schemas/receipt.py` (`uploaded | processing | completed |
failed | confirmed`), the model should default to it, and R5 should copy it. R5's polling
stop condition depends on this being exact.

---

## 3. Minor

- **ARCHITECTURE.md describes a system that was not built.** Traefik, Celery, Ollama
  fallback, store parsers, `/api/receipts/batch`, `/api/inventory/reconcile`,
  `/api/scanner/input`, `/api/products/enrich/{id}`. CLAUDE.md sends every agent there for
  "the full design", so agents will build toward the document. Add a short "As built
  (2026-09)" block at the top listing what exists, and mark the rest as deferred.
- **Three different default models.** `config.py` says `qwen3-8B`, `.env.example` says
  `Qwen3-4B-Instruct`, `stack.env.example` says `qwen3-8B`. R4 should leave exactly one.
- **`ReceiptExtraction` carries deprecated duplicate fields** (`store_name`, `country`, …)
  for a schema that no longer exists. R1 rewrites this model; drop them.
- **`_extract_json_from_response`** falls back to the first `{ … }` span in the reply. With
  thinking disabled and `response_format` set this becomes dead code; keep it only as a
  guarded fallback with a log line so silent partial parses are visible.
- **`InventoryItem.receipt_id`** is set on confirm but there is no index-backed way to get
  "items from this receipt" in the API; R7's read-only confirmed view would want it.
- **Frontend `InventoryListParams`** declares `context` and `category` filters that the
  backend does not implement. Remove or implement in S2.
- **`docs/README.md` Quick Start** clones `fridge-logger` and opens `https://`. Point it at
  `docs/DEPLOY.md` once F2 writes it.
- **Line endings.** `backend-ci.yml` and `requirements.txt` are stored with CRLF; with
  `core.autocrlf=true` the F1 commit will rewrite every line. A `.gitattributes` with
  `* text=auto eol=lf` and a one-time normalisation commit would stop this recurring.
- **The `/components-demo` link in the header** is on the plan for P1 removal; it is also
  reachable from the iPad now, which is harmless.

---

## 4. Alternatives evaluated

| Question | Plan | Alternative | Recommendation |
| --- | --- | --- | --- |
| Async processing | `BackgroundTasks` in the API process | Keep Celery | Plan is right. Celery adds a second process, a broker contract and a deploy surface for one job a day. Add stale-state recovery (S2). |
| Real-time | Polling (30 s list, 3 s receipt) | WebSockets now | Plan is right for MVP. The broadcast plumbing exists and is cheap to wire later; polling has zero client complexity and survives iOS backgrounding. |
| Extraction | LLM-only, one call per receipt | Deterministic line parser only | Keep the LLM primary, but add a heuristic **fallback** that turns `NAME  PRICE` lines into rows (the grammar for S-Group, K-Group and Lidl is already in ARCHITECTURE.md's appendix). It guarantees the review screen has rows when the LLM fails or times out, which is the difference between "fix a few" and "start over". Roughly 60 lines of regex plus tests. |
| Category suggestion | Ask for `suggested_category` inside the main extraction call | A second small call: names in, categories out, JSON-schema-constrained enum; preceded by a Finnish keyword map (`maito` → dairy, `juusto` → cheese, `jauheliha`, `kana`, `broileri` → meat, `leipä` → bread, `pakaste` → frozen, …) | Prefer the two-step form. It keeps the main call short (C1), lets category inference retry independently, and once aliases exist (C2) most items skip it entirely because the matched product already has a category. |
| Frontend to API | CORS with a build-time API URL | Same-origin rewrite through the Next server | Rewrite (S5). |
| Product identity | Fuzzy on `canonical_name` only | Alias table as first-pass memory | Alias (C2). |
| Hiding empty/discarded | Client-side in S2 | Server-side `active=true` default | Server-side. It is a one-line filter, keeps the 30 s polling payload small on a device that never sleeps, and makes the API's default match what the iPad shows. |
| Product name on items | Second request for the product list (current `page.tsx`) | Join in the response (S1) | S1 as planned, plus `category` and `icon`, so S2 needs no products fetch at all. |
| TLS | Deferred, Traefik when needed | Caddy | Not an MVP question. When it comes, Caddy with an internal CA is materially simpler than Traefik for a single host, and the same-origin choice in S5 means one certificate. |

The one place where the plan's chosen approach is genuinely at risk is extraction. The plan's
own R4 acceptance ("5/5 under 120 s, ≥ 80 % of lines") is the right bar. The
recommendation is not to change the architecture but to test it first (C1) and give it a
floor (the heuristic fallback) so a bad LLM day degrades to "more editing" rather than "no
receipt".

---

## 5. What the plan gets right

- Ordering everything by distance to the iPad, and naming the three capabilities that define
  value, is the correct framing and should not be reopened.
- Excluding offline mode, service worker, TLS, WebSockets, barcode scanning, shopping list
  UI, Home Assistant and Mealie from MVP is right in every case.
- `<input type="file" capture="environment">` over plain HTTP is the only camera path that
  works on iOS without TLS; the plan got this right where FRONTEND_PLAN.md did not.
- Making S1 return `product_name` removes the current products-list workaround on the home
  page.
- The R3 202-plus-poll shape is simple and testable; the 409 on double process is right once
  S2's recovery is added.
- The increment sizes are realistic, R7 at 12 h is honestly the largest, and the
  backend-critical-path observation (R1 → R2 → R3 → R5 → R7) is accurate.
- Dropping Zustand for MVP is correct; TanStack Query plus React context covers every listed
  need.

---

## 6. Recommended amendments to the increment plan

Ordered by wave. None of these change the milestone or the waves; they change what is inside
a few increments and move one spike forward.

| ID | Change |
| --- | --- |
| **MVP-F1** | Add `.gitattributes` (`* text=auto eol=lf`) and normalise in its own commit so the CI and requirements diffs are readable. |
| **MVP-F2** | Remove `celery-worker` from both compose files and delete `celery_app.py` (S1). Same-origin `/api` rewrite instead of `NEXT_PUBLIC_API_URL` and `ALLOWED_ORIGINS` (S5). Drop Postgres and Redis host ports (S10). Add `alembic check` to CI and a migration for the `off_product_id` unique constraint (S6). |
| **New: MVP-R0** (Wave 1, 2 h, spike, no code merge required) | LLM feasibility on the homelab with the real receipt text: thinking off, `max_tokens` 4096, trimmed prompt, pre-filtered lines, chunking if needed (C1). Output: a `curl` script in `docs/vLLM_MANUAL_TEST.md` that completes the 60-line receipt under 60 s, or a DEC. R4 keeps the five-receipt validation through the deployed stack. |
| **MVP-S1** | Serialise `Decimal` quantities as JSON numbers with a test (C3). Add `category` and `icon` next to `product_name`. Server-side `active` default filter (hide `empty`, `discarded`). Write `consumption_log` on consume and discard (S9). |
| **MVP-R1** | Alias-first matching before RapidFuzz (C2). Canonical unit normalisation `kg→g`, `l→ml`, `unit→pcs` (S4). One `ReceiptStatus` enum (S11). Pre-filled `location` and `storage_type` derived from `suggested_category` (S3). Drop deprecated fields from `ReceiptExtraction`. `MINERU_LANG` setting and a MinerU timeout default (S7, S2). Category suggestion as keyword map plus a small second LLM call rather than inside the main prompt. |
| **MVP-R2** | Write `store_product_alias` on confirm (C2). Location and storage type from category when not overridden (S3). |
| **MVP-R3** | Add `error` and `processing_started_at` columns with a migration; stale `processing` (> 10 min) is treated as `failed`; `/process` allowed on `failed` (S2). |
| **New: MVP-R3b** (Wave 3, 3 h, backend) | Heuristic line-parser fallback (`NAME  PRICE` grammar from the ARCHITECTURE.md appendix) used when the LLM fails or times out, so `completed` always has rows. Marks the receipt `extraction_method = "heuristic"` so R7 can show a hint. |
| **MVP-R5** | Copy the single status enum; types for quantities follow S1's decision. |
| **MVP-R6** | Client-side downscale before upload (S8). |
| **MVP-P2** | Add to the acceptance: iPad Auto-Lock set to Never or Guided Access enabled, because a home-screen web app does not keep the screen on by itself. |
| **docs** | "As built" block at the top of ARCHITECTURE.md; one default `LLM_MODEL`; README Quick Start points at DEPLOY.md. |

Net effect on the estimate: about +8 h (R0 2 h, R3b 3 h, alias work ~2 h across R1/R2,
serialisation and log ~1 h in S1), offset by F2 losing the CORS and URL parametrisation work.
The critical path is unchanged; R0 runs in parallel with F1 and F2.

---

## 7. Open decisions for the operator

These are the choices the review cannot make.

1. **DEC: unit vocabulary.** `ml | g | pcs` (recommended) or keep receipt-native `kg | l`
   with display conversion. Needed before R1 and C2.
2. **DEC: JSON number versus string for quantities.** Backend serialises float (recommended)
   or frontend parses strings. Needed before S1 and C2.
3. **DEC: same-origin rewrite versus CORS.** Recommended rewrite. Needed before F2.
4. **DEC: what happens when the R0 spike fails.** Options: heuristic parser becomes primary
   and the LLM only categorises; switch model (a non-thinking instruct model, or a larger one
   if the homelab GPU allows); or accept chunked multi-call extraction with its latency.
   Deciding the fallback order now avoids stalling Wave 2.

---

## 8. Operator constraints and the reconciled ordering (added 2026-09-13)

Constraints given after the review:

- Input mix is paper receipts first, then mostly digital S-kaupat receipts, with occasional
  K-Supermarket and Lidl paper receipts.
- Kyokki is meant to be a general system, not one household's tool. Generalising features may
  be pushed later in the timeline, but the design must not close them off.

What this settles:

- **The LLM-based, language-agnostic extraction stays as the core.** It is the only path that
  works for a store the system has never seen, which is what "general" requires. Store-specific
  parsers are not an alternative core; they are optional accelerators the adaptive parser spec
  already describes as learned templates. Post-MVP.
- **Paper receipts being the common case makes the Wave 1 spike (R0) more important, not
  less.** OCR plus extraction is on the critical path for the majority of receipts. The spike
  should test two candidates: text LLM after MinerU (current design, with thinking off and the
  trimmed prompt), and a vision model straight from the image. Both are general; whichever
  finishes a 60-line receipt reliably wins. Keep the loser wired as the fallback.
- **The heuristic fallback (R3b) stays, defined as a generic grammar, not per chain.** A
  `NAME … PRICE` line with an optional following quantity or weight line is near-universal on
  receipts worldwide. It guarantees rows on the review screen when the model fails and is
  store-agnostic. Chain-specific rules (K-Plussa lines, Lidl VAT codes) are the post-MVP
  template layer.
- **Drop the Finnish keyword map from the R1 recommendation.** It is household-specific. The
  small, schema-constrained category call to the LLM is the general mechanism, and alias
  learning (C2) makes it rarely needed after the first receipts from a store.
- **Alias learning keyed by `store_chain` is the general memory mechanism** and should stay in
  R1/R2 as recommended. It is what lets any store's abbreviations converge without
  configuration.
- **Digital S-kaupat receipts cost almost nothing.** The upload endpoint accepts PDF and the
  OCR service already routes PDFs to pdfplumber. R6 should offer "choose a file" (accepting
  `application/pdf` and images, no `capture` attribute) beside the camera button, so a PDF
  saved to the iPad Files app can be uploaded. That is the whole change. Loyalty-app imports
  and email ingestion are post-MVP import adapters.
- **Runtime simplification (one worker, no Redis) is deferred.** Redis works today and a general
  self-hosted product may want multiple workers later. Only the crash-looping Celery worker is
  removed in F2.

Resulting priority inside the MVP, highest first: R0 spike (both candidates), alias learning
in R1/R2, the generic heuristic fallback, the unit and serialisation decisions, then everything
else as amended in section 6. Deferred to post-MVP, in this order: learned store templates,
import adapters for digital receipts, runtime simplification.
