# Handoff
Generated-UTC: 2026-09-14T09:00:00Z
Base-SHA: e9b1d4c

## Round delta
- #34 MVP-R1b merged: typed receipt items, alias-first matching, match threshold 80.
- MVP-U1 on `feat/mvp-u1-unit-migration` (PR open): canonical units `dl | tsp | tbsp | g | pcs`
  everywhere. Rulings: convert on write (422 for unknown units); tsp/tbsp not converted to dl.
  Data migration `a4f8c2d91e37` (lossy downgrade: dl → ml only).

## Active PRs and conflicts
- U1 PR. T1 (Telegram bot) and R2 (confirm creates products) start from main after it merges.

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded; other models evict
  it and cold-load 3-4 min). `reasoning_strength` accepts only `xhigh|high|medium|low`; use `low`.
  Only GPU `GPU-a8c640ca-...` is usable.
- Contract: compact `{"s","d","p":[{"n","q","w","c"}]}` with strict `json_schema`; `c` enum = DB
  category ids, listed with display names in the prompt (ids alone left eggs uncategorised).
  Extraction is ~45-60 s per receipt; `/process` is still synchronous until R3.
- Pipeline input: PDF → pdfplumber text; image → MinerU, falling back to vision on
  `OCRUnavailableError` (connect error, timeout, 5xx) or blank text. MinerU was offline on
  2026-09-14, so vision is what actually runs; MinerU back 2026-09-15 for R4's comparison.
- `ocr_structured` is now `{method, store_chain, purchase_date, lines[{name, quantity, weight_kg,
  category}]}`; nothing in the app read the old shape.
- E2E check that passed: rendered 49-line receipt uploaded via `/scan` + `/process` → vision,
  49/49 lines, 11/11 quantities, 10/10 weights, store and date filled, 40 categorised.
- `receipt.image_path` is relative to the API's working directory (`backend/data/receipts`), and
  `tests/api/test_receipts.py` deletes that directory: don't run it during a manual API check.
- Receipt matching stores only matches >= `FUZZY_MATCH_THRESHOLD` (80); weaker fuzzy guesses were
  wrong in the e2e run. Matching loads the catalog once per receipt (`prepare()` + `match_line()`).
- Non-idempotent mutations need `retry: false` (frontend providers retry mutations once).
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory.

- Plan update 2026-09-14: receipts are mostly digital (order PDFs, S-Group/K-Plussa app receipts)
  plus some paper photos, Android phone. New MVP-T1: private Telegram bot as the primary drop-in
  (long polling, chat-id allowlist, SHA-256 duplicate guard). R6 re-scoped to an iPad file picker.

## Next action
Merge U1 and run `alembic upgrade head` wherever a database exists (homelab: take a backup first).
Then T1 (Telegram bot), then R2 (confirm creates products and writes aliases).
