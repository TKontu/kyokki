# Product identity: exact keys only, and every join undoable (CL8)

Status: **design; decisions 1, 2, 3, 6 ruled 2026-10-07; 4, 5 built at the recommended defaults (#198)**. Extends `PRODUCT_RESOLUTION_SPEC.md`.
Base read: `d30cfa3`.

## Why

Operator, 2026-10-06: "Get rid of fuzzy matching. Karelian stew / karjalan paisti should not match
to Karelian pie / karjalanpiirakka. When you have a mismatch and it merges, it is almost impossible
to revert the match, as editing the item originating from the stew edits the pies and vice versa."

**What happened in production** (read-only trace, 2026-10-06):
- S-group receipt 2026-10-06, line `KARJALANPAISTI`: extraction wrote `generic_name: "Karelian pie"`
  (the catalog block in the extraction prompt invites reusing listed names), then selection picked
  the existing pie product (`match_source: selected`). Confirm stocked it on product `14edd43e`.
- That product also holds the rice pies `VUOKSEN RIISIPIIRAKKA 15KPL` of 2026-09-30 and 2026-10-06.
  The cook renamed it to "Karelian stew", so the rice pies now read "Karelian stew" too. A third
  rice-pie line (2026-10-01) went to "Rice cake" (`7a1b19b6`).
- Items have no identity of their own: name, icon, shelf life and display names are read through
  the product (`models/inventory_item.py:89-132`), a date typed on one item teaches the product and
  re-dates the others (`shelf_life_learning.py:140-198`), and nothing can move an item to another
  product (the code assumes it never happens, `shelf_life_learning.py:242`).

## Every path to a join without an exact key

| # | Path | Where |
|---|---|---|
| P1 | Extraction snaps the generic name to a listed catalog name | `llm_extractor.py:98-104`, `receipt_processing.py:1036-1041` |
| P2 | Trigram shortlist → the model picks → that becomes the product (`selected`) | `product_resolution.py:147-203, 401-407`; `product_selection.py:27-39` |
| P3 | Q37: a canonical hit on the (snapped) generic name is forced into the candidates | `product_resolution.py:265-280, 346-359` |
| P4 | Confirm joins an unresolved row by the served generic name, silently | `receipt_confirm.py:181-203` → `generic_products.py:178-192`; `app/receipt/[id]/page.tsx:287` |
| P5 | Confirm learning makes it permanent: an untouched P4 join is stored as a **cook-verified** alias; a kept `selected` result teaches a model alias and a model name | `receipt_confirm.py:253-257, 288-295, 320-349` |
| P6 | Model-taught names are keys for quick add, stock add and lookups (`trust_model=True`) | `generic_products.py:180`, `quick_add.py:46`, `stock.py:197`, `product_lookup.py:119,160` |
| P7 | An alias learned at another chain resolves outright | `product_resolution.py:312-324` |
| P8 | Rename and merge keep old names as cook names, with no record to reverse | `crud/product_master.py:296-321, 536-541` |
| P9 | "New product: X" joins an existing X without a word | `ReceiptItemRow.tsx:198-203` + P4 |

Not identity paths: `rapidfuzz` in `receipt_processing.py:183` (OCR line alignment only);
`MatchingService` (dead apart from `normalize_receipt_name`); `candidates_for` / `ProductSearch`
(suggest only).

## The rule

**One decision point.** `services/product_identity.py` `decide(...) -> Join | Suggestion | New` is
the only code that turns a name into a product id for writing. Receipt resolution, confirm, quick
add, stock add and the bot call it.

**Exact keys (join without a tap):**
- K1 a verified alias for (this chain, normalised printed name);
- K2 a canonical or cook `product_name` equal to the normalised printed name;
- K3 a cook `product_name` equal to the normalised generic name;
- K4 an explicit product id the cook picked.

**Suggestions only (shown, never joined by default):** `selected` picks, unverified or model aliases,
cross-chain aliases, model names, the Q37 generic-name hit, trigram candidates.

**Confirm contract.** Each row sends `{product_id}` or `{new: name, category}`. A `new` name equal to
an existing key answers **409 `name_exists`** and the row asks "Use Karelian pie, or name this one
differently?". The served generic name is never looked up silently (removes P4, P9). Cook/verified
provenance only for a tap, an accepted suggestion or a typed name; an accepted suggestion is
recorded as `cook_accepted`.

**Review row:** printed text; default "New: <generic>"; "Suggested: Karelian pie (why: picked by the
model / alias from Lidl / name taught by the model)" with Accept and Search; "Accept all suggestions".

**Bypass-proofing:** `tests/test_layering.py` allows `product_for_name`/`known_names` only in
`product_identity` (and read-only lookup), and writes of `InventoryItem.product_master_id` only in
`product_identity`, `product_split` and `crud/product_master`. `build_inventory_item` takes a
`Join` value only `product_identity` constructs. DB CHECKs on the source enums. `trust_model=False`
wherever a join is written.

**Provenance per join** on `inventory_item`: `join_source` (`created | alias | name | cook_pick |
accepted_suggestion | quick_add | agent | merge | split | legacy`), `join_key`, `join_alias_id`,
`join_name_id`, `receipt_line_id`. On aliases and names: `origin_receipt_id`, `origin_line_id`.

## Undoing a wrong join: split (recommended)

Item sheet: **"This is not Karelian pie…"** → an existing or new product (default: the line's own
generic name and category) → "Also move the N other items that came via KARJALANPAISTI
(S-group)" (by `join_alias_id` / `join_key` / normalised printed text for legacy rows).

`services/product_split.py`, one transaction:
1. Move the items; re-point their `consumption_log` rows (run-out and undo follow).
2. Re-point the causing alias to the target as cook-verified (the cook just said what the printed
   name is); re-point or forget the names that the moved lines taught. The canonical name never moves.
3. Re-learn shelf life on both products; the new product starts from the moved line's own estimates.
   If the source keeps a cook shelf life with no observations left, ask: keep or reset.
   Recompute calculated expiries on both.
4. Display names, emoji, icon, min stock and shopping rows stay with the source; the new product
   goes through the normal new-product pipeline (estimates, display name, emoji, icon).
5. Record a `product_reassignment` row (from, to, items, alias/name changes); **Undo split** replays it
   backwards. Merge records one too, which makes **un-merge** possible.
6. Broadcast `inventory_update` for the items and `product_update` for both products.

Rejected: per-item overrides (every read path and all learning would need override logic, and the
next receipt would still join wrongly); a variant layer (a third identity level for one household;
provenance gives its benefit without a new editable object).

## Migration and repair

One revision: the provenance columns, `origin_*` on alias and name, `product_reassignment`, CHECKs
after the backfill. Backfill from `receipt.ocr_structured` (`line_id`, `match_source`, printed
name) via `receipt_line_index` (Q26 onward; older rows `legacy`). A read-only
`scripts/audit_product_joins.py` lists products whose items came via different printed names,
`selected` or suspect joins, model names and unverified aliases, with a suggested split.

## Lanes

| Lane | What | Depends |
|---|---|---|
| L0 | Migration, models, backfill | — |
| L1 | `product_identity`, resolution/confirm/quick add/stock add on it, 409 contract, layering tests | L0 |
| L2 | Split / undo split / un-merge service and API | L0 |
| L4 | Audit script | L0 |
| L3 | Review-row suggestions, 409 prompt, item-sheet split flow, product sources list | L1, L2 contract |

Acceptance: "KARJALANPAISTI never resolves to Karelian pie" (with a selection stub that always picks
candidate 0, and one that fails); confirm with a served "Karelian pie" → 409; quick add "karelian
stew" with a model name present → new product; "split restores both products' shelf lives"; merge →
un-merge round trip; the next receipt resolves the printed name to the split target by key.

## Operator decisions

1. Suggested matches: unticked until accepted, plus "Accept all" (recommended), or pre-ticked?
2. A verified alias from another chain: join outright, or suggest only (recommended)?
3. Rename: keep the old name as a synonym by default (today always)?
4. Split leaving the source with no observations: ask each time (recommended), keep, or reset?
5. Split: copy min/reorder stock to the new product? Recommended no.
6. Drop the catalog block from the extraction prompt (the source of P1), or keep it for category
   hints now that the generic name can never be a key?

## Rulings (operator, 2026-10-07)

1. Suggestions are **unticked**, with "Accept all" on the review screen.
2. A verified alias from **another chain only suggests**.
3. Rename **asks** whether to keep the old name as a synonym.
6. The extraction catalog block **stays as a hint**; the generic name it yields never decides the product.
4, 5 (split): as built in #198 - report `observations_left`, no automatic reset; no min-stock copy.
