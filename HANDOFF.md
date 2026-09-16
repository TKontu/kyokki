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

## Deployment (2026-09-16)
- `.github/workflows/images.yml` publishes `ghcr.io/tkontu/kyokki-backend` and `-frontend` on
  every push to main (`latest` + `sha-<commit>`). The packages must be public once.
- `docker-compose.prod.yml` builds nothing: it pulls those images and takes configuration from
  environment variables (Portainer stack env; `stack.env.example` is the paste-ready list).
  `docker-compose.build.yml` is the local-build override.
- A one-shot `kyokki-migrate` service runs `alembic upgrade head` + the category seed before the
  API, worker and bot start, so a Portainer redeploy needs no console step. It shows as
  `Exited (0)`.
- Receipt files and logs are named volumes (`kyokki_data`, `kyokki_logs`), not host paths.
- Verified locally with the build override: migrations ran, all services came up, and a receipt
  went through MinerU + `c2.muse-glimmer` in 65 s.
- The repo is public, so GitHub-hosted Actions minutes are free; a self-hosted runner with a
  mounted Docker socket would be a security risk on a public repo (fork PRs run arbitrary code).

## Receipt review (2026-09-16)
- `/receipt/[id]` is the review screen and `ReceiptsBanner` on the home page is the way in.
  That closes the loop the operator asked for: drop a receipt to the bot, review it, stock
  appears, consume it.
- Receipt data lives in `lib/api/receipts.ts` + `hooks/useReceipts.ts`; polling is in the pure
  helpers `detailPollInterval` / `listPollInterval`, so tests never wait on real timers.
- A line with no category starts skipped; picking one includes it. Matched lines go to their
  product and need no category.
- Still open in Wave 4: R6 (iPad upload page) and R8 (receipts list). Attaching an existing
  product per line is also deferred until the catalog is worth searching.
