# Handoff
Generated-UTC: 2026-09-14T03:00:00Z
Base-SHA: 7de543e

## Round delta
- #29 MVP-C2 merged: ConsumptionSheet, list-wide optimistic consume with rollback and no retry,
  client reads FastAPI `detail`, msw for Jest.
- MVP-S2 on `feat/mvp-s2-stock-view` (PR open): grouped stock view (Expiring soon, Fridge,
  Freezer, Pantry, Other), stable sort on client and server, products fetch removed.
  Ruling: pinned items are not repeated in their location group.

## Active PRs and conflicts
- MVP-S2 PR. Touches `InventoryList.tsx`, `InventoryItemCard.tsx`, `app/page.tsx`,
  `lib/consumption.ts`, `backend/app/crud/inventory_item.py`. S3 and S4 both add UI to the home
  page and card, so start them from main after S2 merges.
- Worktree `C:/code/Kyokki-docs` still holds merged `docs/mvp-plan-review-amendments`; removable.

## Non-obvious decisions or blockers
- Stock rules live in `lib/stock.ts`; the list only renders `buildStockView`. Client hiding of
  inactive items is deliberate: an optimistic Done removes the card before the refetch.
- Ordering tests must UPDATE rows before listing: Postgres returns ties in insertion order on
  fresh tables, so a naive test passes without a tie-breaker.
- Locations are free strings in the API. S4's "move location" should offer only the three known
  values; unknown ones already render under "Other".
- `receipts.py` confirm still hardcodes `location="main_fridge"` (R2 fixes it via category mapping).
- Non-idempotent mutations need `retry: false` (providers retry mutations once).
- Before a browser check: stop old dev servers (the Next child survives stopping the npm task),
  `rm -rf .next`, never build while dev runs. Window resize above the screen size fails; the
  default automation viewport is 1280 wide, which already exercises the `lg` two-column layout.
- Manual API runs: throwaway database, move root `.env` aside only while uvicorn starts.
- DEC-1 left ml, l and kg out; confirm conversion factors before R1.
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory, run the R0 spike.

## Next action
Operator merges the S2 PR. Then S3 (quick add) or S4 (item edit sheet); S4 is smaller and gives
the fix-a-mistake path that C2's no-Undo ruling relies on. R1/R2 remain gated on R0, DEC-4 and the
DEC-1 conversions.
