# Handoff
Generated-UTC: 2026-10-06T19:36:34Z
Base-SHA: 3f27f980605ef801d8dea7b8b4eebd41abea4bcb

## Round delta
- Round 2026-10-06-2 merged (#191 to #194), **not deployed** (nor are 2026-10-04-2 and 2026-10-06-1):
  bot shopping/consume commands (CL3), run-out as a shopping source (CL6), icon spike Q18-S2 (no
  winner; Q18-S3 proposed). CL8 design: `docs/PRODUCT_IDENTITY_SPEC.md`.
- Pending deploy step: `KYOKKI_PUBLIC_URL` in the homelab `.env`; migration `d8f3a61c2b57`.

## Active PRs and conflicts
- Only this reconcile.

## Non-obvious decisions or blockers
- **The planner cannot merge**; the operator merges.
- **Production data is wrong now:** product `14edd43e` "Karelian stew" holds the stew and two rice-pie
  purchases (VUOKSEN RIISIPIIRAKKA 30.9, 6.10). The CL8 split (or a manual fix) repairs it.
- CL8 L1 (the exact-key rule) waits on spec decisions 1, 2, 6; L2 split uses the spec's recommended
  defaults for 4 (ask) and 5 (no min-stock copy) unless the operator says otherwise.
- A migration lane owns the `tests/db/` only-head and table-count tests.
- Open rulings: CL1 bot confirm, CL4 catalog scope, bought-adds-stock, pieces-open, Q18-S3.

## Next action
`/plan-round`: CL8 L0+L2 (schema, backfill, split API), L3 split UI against the same contract, L4 audit.
