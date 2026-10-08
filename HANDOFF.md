# Handoff
Generated-UTC: 2026-10-07T18:51:49Z
Base-SHA: abf930880c75807530a99b37d77ae6e670b71f8b

## Round delta
- Round 2026-10-06-3 (CL8 split/undo, join audit) is deployed. The operator split the rice pies
  to "Karjalan piirakka".
- #200 merged, **not deployed**: iPad sheets no longer let touches scroll the page (shared body
  lock), and the product sheet shows fresh values after a save. Needs an on-device check (TODO).
- CL8 rulings recorded in `docs/PRODUCT_IDENTITY_SPEC.md` "Rulings": unticked suggestions + Accept
  all; other-chain aliases suggest only; rename asks; catalog block hint-only.

## Active PRs and conflicts
- Only this handoff.

## Non-obvious decisions or blockers
- **The planner cannot merge**; the operator merges every PR.
- **Android workstream ON HOLD** until the operator re-initiates it.
- CL8 L1 touches confirm, resolution, quick add, stock add and the bot lookup, plus the review row
  and the rename sheet: give one lane the backend, one the frontend (it owns `lib/i18n`), and fix
  the confirm/suggestion API contract first. `inventory_item.join_source`/`join_key` exist, unused.
- A migration lane owns the `tests/db/` only-head and table-count tests.
- Still open rulings: CL1 bot confirm, CL4 catalog scope, bought-adds-stock, pieces-open, Q18-S3.

## Next action
`/plan-round` for CL8 L1 from `docs/PRODUCT_IDENTITY_SPEC.md` (sections "The rule" and "Rulings").
