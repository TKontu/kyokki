# Handoff
Generated-UTC: 2026-09-14T20:30:00Z
Base-SHA: d77c849

## Round delta
- #41 MVP-S4 merged: item edit sheet (correct, mark as gone, delete with history).
- MVP-R3b on `feat/mvp-r3b-heuristic-fallback` (PR open): a store-agnostic line parser reads text
  receipts when the model fails or finds nothing (`extraction_method = "heuristic"`,
  `fallback_reason`). Heuristic receipts can be re-read with `/process`. No migration.

## Active PRs and conflicts
- R3b PR. Wave 3 then has only R4 (real-receipt validation on the homelab), which needs the
  deployed stack and MinerU. Wave 4 (R5-R8 receipt screens) starts when Wave 3 is merged; the
  operator can decide to start Wave 4 before R4 if homelab deployment waits.

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded, one slot).
  `reasoning_strength` only `xhigh|high|medium|low`; use `low`. Only GPU `GPU-a8c640ca-...`.
  MinerU was still unreachable on 2026-09-14, so images use vision (no heuristic fallback there).
- Heuristic parser: `app/parsers/heuristic.py`; skip list shared with the LLM prefilter in
  `app/parsers/receipt_lines.py`. Test fixtures in `backend/tests/fixtures/receipts/`.
- Products are generic English names; heuristic rows have none (names as printed), so only
  aliases and printed-name matches apply until the model re-reads.
- Receipts: queue `queued -> processing -> completed | failed -> confirmed`; `kyokki-worker` must
  run (locally `python -m app.worker`).
- Stock status rules live in `crud/inventory_item.apply_quantity_status` (consume + corrections).
- Agent track (HTTP API + `kyokki` CLI + SKILL.md, no MCP, agent on the LAN) is planned in
  `docs/agent_TODO.md` and starts after MVP-P3.
- Always run backend pytest through the scratch `rt.sh` (moves the legacy root `.env` aside);
  a direct run prints the legacy `.env` values in the settings error.
- Browser checks: the automation tab is hidden; drive the UI with `javascript_tool`.
- Non-idempotent mutations (consume, delete, confirm, quick add) use `retry: false`.
- Operator items still open: rotate Postgres password + LLM key (and the legacy root `.env`
  keys), purge `stack.env` history, deploy on the homelab and confirm the iPad renders
  inventory, create the Telegram bot.

## Next action
Merge R3b. Then R4 on the homelab (deploy, MinerU, five real receipts), or ask the operator to
start Wave 4 (R5 receipt API module and polling hooks) while R4 waits for the homelab.
