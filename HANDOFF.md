# Handoff
Generated-UTC: 2026-09-14T16:30:00Z
Base-SHA: cdee956

## Round delta
- #38 MVP-R3 merged: Postgres receipt queue and `kyokki-worker`.
- MVP-S3 on `feat/mvp-s3-quick-add` (PR open): "+ Add" sheet on the home page adds stock for an
  existing or new generic product. Ruling: one backend call `POST /api/inventory/quick-add`
  instead of two frontend calls. Product rules shared with confirm in
  `services/generic_products.py`; categories expose `default_storage`. No migration.

## Active PRs and conflicts
- S3 PR. Wave 3 left after it: S4 (item edit sheet), R3b (heuristic fallback), R4 (homelab
  validation; needs the deployed stack and MinerU).

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded, one slot).
  `reasoning_strength` only `xhigh|high|medium|low`; use `low`. Only GPU `GPU-a8c640ca-...`.
  MinerU was still unreachable on 2026-09-14.
- Products are generic English names (R2). Quick add and confirm reuse a product by
  case-insensitive name; new products take shelf life/storage from the category and get a
  capital first letter.
- Receipts: queue `queued -> processing -> completed | failed -> confirmed`; `kyokki-worker` must
  run (locally: `python -m app.worker`). Tests use `run_once(session_factory)`.
- Browser checks: the automation tab is hidden, so extension clicks/typing are unreliable; drive
  the UI with `javascript_tool` (see memory). Hidden radio inputs need `relative` labels.
- Non-idempotent mutations (consume, confirm, quick add) use `retry: false`.
- `tests/api/test_receipts.py` deletes `backend/data/receipts`: don't run it during a manual check.
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, create the Telegram bot.

## Next action
Merge S3. Then S4 (edit sheet: quantity, expiry, location, mark gone, delete) or R3b; R4 once the
homelab stack and MinerU are up. Wave 4 (R5-R8 receipt screens) starts when Wave 3 is merged.
