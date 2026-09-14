# Handoff
Generated-UTC: 2026-09-14T11:30:00Z
Base-SHA: 217b43f

## Round delta
- #36 MVP-T1 merged: Telegram receipt drop-in bot and SHA-256 duplicate guard.
- MVP-R2 on `feat/mvp-r2-confirm-generic-products` (PR open): generic products, confirm creates
  or reuses them, learns aliases. Rulings: products are generic (no brand, fat content or cut),
  English names first; only `completed` receipts confirm (409 otherwise); aliases keyed by line
  index. No migration.

## Active PRs and conflicts
- R2 PR. Wave 2 is complete once it merges. Wave 3 next: S3, S4, R3, R3b, R4 (T1 and S2 done).

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded, one slot; other
  models evict it and cold-load 3-4 min). `reasoning_strength` only `xhigh|high|medium|low`; use
  `low`. Only GPU `GPU-a8c640ca-...` is usable.
- Contract is now `{"s","d","p":[{"n","g","q","w","c"}]}`; `g` is the generic English name and
  the prompt lists up to 300 catalog names for reuse. A 49-line receipt needs ~3.8k completion
  tokens, so `LLM_MAX_TOKENS` defaults to 8192. Extraction is ~40-70 s; `/process` is synchronous
  until R3.
- Matching order: printed-name alias → exact generic name → exact printed name → fuzzy (80).
  The e2e second receipt with other brands matched 11/12 on generic names.
- Confirm (`services/receipt_confirm.py`) is one transaction with `SELECT ... FOR UPDATE` on the
  receipt; any invalid item rolls back. Product reuse is a case-insensitive name match; there is
  no unique constraint on names or aliases (lookup upsert, serialised by the row lock).
- Vision misreads become wrong generic names (SIENILIINA → Mushroom). R7's review screen is where
  they get fixed; the text path (PDF, MinerU) named them correctly.
- Pipeline input: PDF → pdfplumber; image → MinerU, falling back to vision on
  `OCRUnavailableError` or blank text. MinerU back 2026-09-15 for R4's comparison.
- Telegram bot: `kyokki-telegram` service, long polling, sequential in-memory queue (R3 replaces
  it). Real-bot manual check still needs the operator's @BotFather token.
- Identical file bytes are a duplicate upload (409 / "Already received"); tests that upload
  several receipts must use distinct content. `tests/api/test_receipts.py` deletes
  `backend/data/receipts`: don't run it during a manual API check.
- Non-idempotent mutations need `retry: false` (frontend providers retry mutations once).
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, create the Telegram bot.

## Next action
Merge R2. Existing homelab products (if any) keep their old branded names; rename them to generic
names by hand or let new receipts create generic ones. Then Wave 3: R3 (background processing)
is the natural next backend step, S3/S4 on the frontend.
