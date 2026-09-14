# Handoff
Generated-UTC: 2026-09-14T14:10:00Z
Base-SHA: c0ae70b

## Round delta
- #37 MVP-R2 merged: generic products, confirm creates/reuses products and learns aliases.
- MVP-R3 on `feat/mvp-r3-receipt-queue-worker` (PR open): uploads are queued in Postgres and a new
  `kyokki-worker` service reads them one at a time. Rulings: DB queue + one worker instead of
  BackgroundTasks; uploads queue automatically, `/process` only retries. Migration
  `c3e9a7b5d1f2` (queued_at, processing_started_at, error).

## Active PRs and conflicts
- R3 PR. Wave 3 left after it: S3, S4 (frontend), R3b (heuristic fallback), R4 (homelab
  validation, needs MinerU and a deployed stack). R5 (frontend receipt hooks) unblocks after R3.

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded, one slot; other
  models evict it and cold-load 3-4 min). `reasoning_strength` only `xhigh|high|medium|low`; use
  `low`. Only GPU `GPU-a8c640ca-...` is usable. MinerU was still unreachable on 2026-09-14, so
  images take the vision path.
- Queue: status `queued → processing → completed | failed → confirmed`; `uploaded` only on old
  rows. Claim is `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)`. Stale `processing`
  (> `RECEIPT_STALE_MINUTES`, 10) is failed by the worker loop and on receipt GET/list/process.
  A worker killed mid-read may finish later only if restarted; the receipt otherwise waits for
  the stale limit, then `/process` re-queues it.
- Without `kyokki-worker` running, receipts stay `queued` forever. Local dev: run
  `python -m app.worker` next to uvicorn.
- Tests that need a processed receipt call `app.worker.receipt_worker.run_once(session_factory)`
  (fixture in `tests/conftest.py`) instead of `/process`.
- Telegram bot: enqueues via ingest; `ResultNotifier` polls pending receipts every 3 s and edits
  the acknowledgement. Real-bot check still needs the operator's @BotFather token.
- Products are generic (R2 ruling); contract `{"s","d","p":[{"n","g","q","w","c"}]}`,
  `LLM_MAX_TOKENS` 8192.
- Identical file bytes are a duplicate upload (409 / "Already received").
  `tests/api/test_receipts.py` deletes `backend/data/receipts`: don't run it during a manual check.
- Non-idempotent mutations need `retry: false` (frontend providers retry mutations once).
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, create the Telegram bot.

## Next action
Merge R3; on the homelab `up -d --build` (starts `kyokki-worker`) and `alembic upgrade head`.
Then R5 (receipt API module and polling hooks) to open the R6/R7 path, or S3/S4 on the frontend.
