# Handoff
Generated-UTC: 2026-10-07T14:45:55Z
Base-SHA: 0daf92fce59ce8c6e37502a0d9e17c0bc819da02

## Round delta
- Round 2026-10-06-3 merged and **deployed 2026-10-07** (#196 to #198): CL8 split / undo (API + iPad)
  and `GET /api/audit/product-joins`. Migration `e2a9c4f71b38`. The operator already split the rice
  pies off "Karelian stew" to "Karjalan piirakka".
- Audit on production: 5 products flagged (Rice cake, Rye bread, Cold cuts, Apple, Oat drink); see the
  round block in `docs/TODO.md`.

## Active PRs and conflicts
- Only this reconcile.

## Non-obvious decisions or blockers
- **The planner cannot merge**; the operator merges. **Android workstream ON HOLD** until the operator
  re-initiates it.
- CL8 L1 (exact keys; near names only suggest) waits on `docs/PRODUCT_IDENTITY_SPEC.md` decisions
  1, 2, 6. `inventory_item.join_source`/`join_key` exist but are not written until L1.
- A migration lane owns the `tests/db/` only-head and table-count tests.
- Open rulings: CL1 bot confirm, CL4 catalog scope, bought-adds-stock, pieces-open, Q18-S3.

## Next action
Operator: answer CL8 decisions 1, 2, 6 and review the audit list. Planner: `/plan-round` with CL8 L1.
