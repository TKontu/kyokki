# Handoff
Generated-UTC: 2026-09-14T19:30:00Z
Base-SHA: 3e00902

## Round delta
- #39 MVP-S3 merged (Quick Add); #40 merged (agent interface plan, `docs/agent_TODO.md`,
  post-MVP-P3).
- MVP-S4 on `feat/mvp-s4-item-edit-sheet` (PR open): "Edit" sheet on stock cards to correct
  quantity, expiry and location, mark as gone, or delete. Rulings: delete removes the item and
  its history; quantity edits are corrections (not logged); above the full amount raises it.
  Migration `d5f1b8c2e4a6` (consumption_log FK ON DELETE CASCADE) fixes a 500 on deleting used
  items.

## Active PRs and conflicts
- S4 PR. Wave 3 left after it: R3b (heuristic fallback) and R4 (homelab validation; needs the
  deployed stack and MinerU). Wave 4 (R5-R8 receipt screens) starts when Wave 3 is merged.

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded, one slot).
  `reasoning_strength` only `xhigh|high|medium|low`; use `low`. Only GPU `GPU-a8c640ca-...`.
  MinerU was still unreachable on 2026-09-14.
- Products are generic English names; quick add and confirm share `services/generic_products.py`.
- Stock status rules live in `crud/inventory_item.apply_quantity_status`, used by consume and by
  PATCH corrections. PATCH with an explicit `status` skips them.
- Receipts: queue `queued -> processing -> completed | failed -> confirmed`; `kyokki-worker` must
  run (locally `python -m app.worker`).
- Agent track (Hermes/OpenClaw: HTTP API + `kyokki` CLI + SKILL.md, no MCP, agent on the LAN)
  is planned in `docs/agent_TODO.md` and starts after MVP-P3.
- Browser checks: the automation tab is hidden; drive the UI with `javascript_tool` (see memory).
- Non-idempotent mutations (consume, delete, confirm, quick add) use `retry: false`.
- `tests/api/test_receipts.py` deletes `backend/data/receipts`: don't run it during a manual check.
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, create the Telegram bot.

## Next action
Merge S4 and run `alembic upgrade head` on the homelab. Then R3b (heuristic line parser when
extraction fails), or R4 once the homelab stack and MinerU are up.
