# Handoff
Generated-UTC: 2026-09-14T09:00:00Z
Base-SHA: 5266dee

## Round delta
- #31 R0 spike docs merged (passed on `muse-glimmer`).
- #32 MVP-R1a merged: extraction rewritten to the R0 request,
  vision fallback when MinerU is down, inline category, new settings. Rulings this round: R1 split
  into R1a/R1b, category inline (no second LLM call), conversions `l→dl ×10`, `ml→dl ÷100`,
  `kg→g ×1000`, `unit→pcs`, existing-data migration as its own increment U1 after R1b.

## Active PRs and conflicts
- Plan-update docs PR (Telegram drop-in, T1). No code.

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
- `receipt.image_path` is relative to the API's working directory (`backend/data/receipts`).
- Non-idempotent mutations need `retry: false` (frontend providers retry mutations once).
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory.

- Plan update 2026-09-14: receipts are mostly digital (order PDFs, S-Group/K-Plussa app receipts)
  plus some paper photos, Android phone. New MVP-T1: private Telegram bot as the primary drop-in
  (long polling, chat-id allowlist, SHA-256 duplicate guard). R6 re-scoped to an iPad file picker.

## Next action
R1b (typed `ExtractedItem`, per-item + alias-first matching, units helper,
`ReceiptStatus`, category → location, API `items`, frontend `types/receipt.ts`), then U1.
