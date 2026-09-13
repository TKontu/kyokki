# Handoff
Generated-UTC: 2026-09-14T01:30:00Z
Base-SHA: 1659ace

## Round delta
- #28 MVP-C1 merged: `BottomSheet`, `ToastProvider`/`useToast`.
- MVP-C2 on `feat/mvp-c2-consumption-sheet` (PR open): ConsumptionSheet wired from the home
  page, list-wide optimistic consume with rollback and no retry, API client reads FastAPI
  `detail`, msw set up for Jest. Rulings: no Undo; pieces get −1/−2/−3.

## Active PRs and conflicts
- MVP-C2 PR. Touches `hooks/useInventory.ts`, `lib/api/client.ts`, `app/page.tsx`,
  `jest.config.js`, `jest.setup.js`. S2 will touch `app/page.tsx` and `InventoryList` next.
- Worktree `C:/code/Kyokki-docs` still holds merged `docs/mvp-plan-review-amendments`; removable.

## Non-obvious decisions or blockers
- Non-idempotent mutations must set `retry: false`: `app/providers.tsx` retries mutations once
  by default, and TanStack pauses retries while the page is hidden. S4 (PATCH is idempotent,
  DELETE is not) and R2's confirm should follow the same rule.
- msw: `test/msw/server.ts` is opt-in per file (`server.listen` in the test); older tests still
  mock `global.fetch`. New ESM-only msw dependencies go in `esmPackages` in `jest.config.js`.
- `npm run build` while `npm run dev` is running corrupts the dev server's `.next`: the page
  renders unstyled with no data. Stop dev, `rm -rf .next`, restart. Stopping the background
  npm task does not kill the Next child process; check the port with netstat.
- Manual API runs: move the root `.env` aside only while uvicorn imports settings, then restore
  it; use a throwaway database (`CREATE DATABASE ...`, alembic upgrade, `python -m
  app.db.seed_categories`, drop afterwards).
- The browser screenshot tool renders a hidden tab at the wrong scale; measure the DOM instead.
- Items with equal expiry dates come back in varying order; S2 needs a stable sort.
- DEC-1 left ml, l and kg out; confirm conversion factors before R1. TS `Unit` is still
  `ml | g | pcs | unit`.
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, run the R0 spike.

## Next action
Operator merges the C2 PR. Wave 2 is then done except R1/R2 (gated on R0, DEC-4, DEC-1
conversions). Wave 3 frontend is unblocked: S2 (stock view), S3 (quick add), S4 (edit sheet).
