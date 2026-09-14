# Handoff
Generated-UTC: 2026-09-14T18:00:00Z
Base-SHA: 786a891

## Round delta
- #35 MVP-U1 merged: canonical units `dl | tsp | tbsp | g | pcs`, convert on write.
- MVP-T1 on `feat/mvp-t1-telegram-bot` (PR open): private Telegram receipt drop-in bot plus a
  SHA-256 duplicate guard on both upload channels. Rulings: the reply is a summary plus unmatched
  names; duplicates are rejected on both channels (API 409 with the existing `receipt_id`).
  Migration `b7d3e5f1a2c4` adds `receipt.content_sha256`.

## Active PRs and conflicts
- T1 PR. R2 (confirm creates products and writes aliases) starts from main after it merges.

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded; other models evict
  it and cold-load 3-4 min). `reasoning_strength` accepts only `xhigh|high|medium|low`; use `low`.
  Only GPU `GPU-a8c640ca-...` is usable.
- Contract: compact `{"s","d","p":[{"n","q","w","c"}]}` with strict `json_schema`; `c` enum = DB
  category ids, listed with display names in the prompt. Extraction is ~45-60 s per receipt;
  `/process` is still synchronous until R3.
- Pipeline input: PDF → pdfplumber text; image → MinerU, falling back to vision on
  `OCRUnavailableError` or blank text. MinerU back 2026-09-15 for R4's comparison.
- Telegram bot: `python -m app.telegram_bot` (`kyokki-telegram` service). Long polling, one
  sequential worker with an in-memory queue (R3 replaces it with the background job). Bot API URLs
  carry the token, so httpx logging is set to WARNING and errors never include URLs. It idles
  without `TELEGRAM_BOT_TOKEN`. Real-bot manual check not done yet: needs the operator's token.
- Uploading identical bytes is now a duplicate. Tests that upload several receipts must use
  distinct content.
- `receipt.image_path` is relative to the API's working directory (`backend/data/receipts`), and
  `tests/api/test_receipts.py` deletes that directory: don't run it during a manual API check.
  The bot and API share `./data` in compose, so both see the same files.
- Receipt matching stores only matches >= `FUZZY_MATCH_THRESHOLD` (80).
- Non-idempotent mutations need `retry: false` (frontend providers retry mutations once).
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, create the Telegram bot.

## Next action
Merge T1, run `alembic upgrade head` on the homelab, create the bot per `docs/DEPLOY.md` and share
an S-kaupat PDF and a K-Plussa screenshot. Then R2 (confirm creates products and writes aliases).
