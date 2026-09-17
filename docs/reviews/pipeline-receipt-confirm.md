# Pipeline Review: POST /api/receipts/{id}/confirm

Reviewed at 23b83ad (same tree as origin/main e233db5, 2026-09-17).

Scope: the review page's "Add n items" tap through the confirm endpoint, product resolution,
inventory creation, alias and non-food learning, the commit, and the broadcasts. Includes the
frontend payload builder because the contract (indexes, units, `non_food_indexes`) is decided
there. Quick add shares the product seam and was read for that reason only.

## Flow
frontend/app/receipt/[id]/page.tsx:submit → hooks/useReceipts.ts:useConfirmReceipt
→ api/endpoints/receipts.py:confirm_receipt (handle_integrity_errors)
→ schemas/receipt.py:ConfirmedItemCreate (unit canonicalised, product_id | name | index)
→ services/receipt_confirm.py:confirm_receipt (SELECT … FOR UPDATE on the receipt)
  → _Confirmation.add per item → line → ProductResolver.resolve (generic_products.py)
    → build_inventory_item → quantity_for_product → InventoryItem
  → learn_alias (store_product_alias) → _remember_skipped_non_food (non_food.py)
  → receipt.processing_status = confirmed → commit
→ broadcast_inventory_update per item, broadcast_receipt_status

## Critical (must fix)
None found.

## Important (should fix)
- [ ] backend/app/api/endpoints/receipts.py:168-197 and
      backend/app/services/receipt_queue.py:393-405 — **A confirmed receipt can be re-queued
      and confirmed again.** `/process` checks the status with a plain SELECT, then `enqueue`
      writes `queued` unconditionally. Its UPDATE waits on confirm's row lock and then lands
      *after* confirm committed `confirmed`. On a heuristic receipt the review page shows
      "Read again with the model" and "Add n items" on the same screen; tapping both within a
      second (iPad double-tap, or one on each device) makes the receipt `queued` with its
      inventory already created, the worker reads it back to `completed`, and the cook is
      offered the same lines a second time. Fix: `enqueue` should be a conditional
      `UPDATE … WHERE processing_status IN (…)` (or `/process` should lock the row) so a
      receipt that became `confirmed` in between is refused.
- [ ] frontend/app/receipt/[id]/page.tsx:155,184 and backend/app/services/non_food.py:30-66
      — **A model misjudgement becomes a permanent non-food memory without the cook seeing
      it.** The page folds every line the model flagged `household` away and sends all of them
      as `non_food_indexes`; the backend remembers each one and nothing ever forgets. When the
      model wavers on frozen berries or eggs (the handoff records it wavering on category
      names), the cook confirms without expanding the fold, and from then on every receipt
      hides that product as household; including it later does not clear the memory. Fix:
      remember only lines the cook has actually seen as household (or only those flagged by
      memory already), and delete the `non_food_name` row when a remembered line is confirmed
      with an `index`.

## Minor
- [ ] backend/app/services/generic_products.py:98-112 and
      backend/app/models/product_master.py:32 — No unique constraint on
      `lower(canonical_name)`. Two confirms (or a confirm and a quick add) that create the same
      new generic name concurrently both insert; afterwards the resolver silently picks the
      oldest, so the duplicate is invisible on the review path but shows twice in product
      search and splits stock between two products.
- [ ] frontend/app/receipt/[id]/page.tsx:65,226-229 — `edits` is keyed by line index and is
      never cleared. After "Read again with the model" the worker replaces `ocr_structured.lines`
      and the same component stays mounted, so a name or category edited on old line 3 is
      applied to whatever the model now puts at index 3. Reset `edits` when
      `extraction_method` or the line set changes.
- [ ] backend/app/services/receipt_confirm.py:118-135 and backend/app/services/non_food.py:40-51
      — One SELECT per line for the alias and one per remembered name, all inside the receipt
      row lock. A 50-line receipt is ~150 statements in the transaction. Fine for one household;
      load the chain's aliases once if it ever matters.

## Verified sound
- Double confirm is impossible: `SELECT … FOR UPDATE` on the receipt, the second caller waits
  and gets 409 "already confirmed" (receipt_confirm.py:209-221); the mutation has `retry: false`.
- All-or-nothing: one commit at the end; any exception (invalid item, integrity error) rolls
  back, and constraint errors are mapped to 400/409 by `handle_integrity_errors`.
- Unit handling: `ConfirmedItemCreate` canonicalises before the service runs, an unknown unit
  is a 422 with nothing written, and the piece conversion is not applied twice (the page
  already sends `pcs`; the backend converts only `g` for a product counted in pieces).
- New products validate the category before insert; an out-of-range `index` or unknown
  `product_id` is a 400 with nothing written.
- Alias learning keeps one row per (chain, printed name): created verified, reinforced on
  repeat, corrected when the cook picks another product, and the same name twice on one receipt
  yields one alias.
- Two identical non-food names in one confirm do not hit `uq_non_food_name`: autoflush before
  the second lookup finds the pending row.
- `_fill_gaps` never overwrites a known piece weight or opened shelf life.
- Broadcasts run after the commit, and the log line carries counts and ids only.
