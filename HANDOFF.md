# Handoff
Generated-UTC: 2026-10-06T09:04:25Z
Base-SHA: d30cfa3c0851ca9ced851f7d4aed0c95113de229

## Round delta
- Rounds 2026-10-04-2 and 2026-10-06-1 merged (#183 to #190), **neither deployed**.
  - 10-04-2: Android share target, several receipts per upload, shims removed, a flaky test fixed.
  - 10-06-1: restock ticks shopping rows bought (CL2); date edits say what they taught and refresh
    the product (CL7); durable Telegram results for every source plus review links (CL5).
- Migration `d8f3a61c2b57` (`telegram_receipt_message`); new setting `KYOKKI_PUBLIC_URL`.
- Log: `.rounds/2026-10-06-1/round.md`; outcomes in `docs/TODO.md` round blocks.

## Active PRs and conflicts
- Only this reconcile.

## Non-obvious decisions or blockers
- **The planner cannot merge** (`gh pr merge` is denied); the operator merges.
- A migration lane must also own `tests/db/` only-head and table-count tests.
- Approved for the next round: **Q18-S2** icon style spike (contact sheet; "Flat" stands until the
  operator picks). Plannable now: CL3 (bot shopping/consume), CL6 (run-out feeds shopping).
- Rulings still open: bought tick adds stock?; bot confirms matched lines unseen (CL1)?; CL4
  catalog = shared defaults or household backup?; partial use of pieces opens the rest?
- `lib/i18n/{en,fi}.ts`: one frontend lane per round. No Docker in the container; PostgreSQL 16
  and Redis are apt-installed and may vanish on reboot.

## Next action
Operator: set `KYOKKI_PUBLIC_URL` and deploy d30cfa3. Planner: `/plan-round` with Q18-S2, CL3, CL6.
