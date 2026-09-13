# Handoff
Generated-UTC: 2026-09-13T21:30:00Z
Base-SHA: 8ae8ac8e9dc4a2f5353fae4875b7c8dad90f4f89

## Round delta
- #24 MVP-F1 and #26 MVP-F2 merged; #25 plan-review amendments merged (see git log).
- Operator rulings this session: DEC-1 unit vocabulary `dl | tsp | tbsp | g | pcs`;
  DEC-2 quantities are JSON numbers. Both recorded in `docs/TODO.md`.
- MVP-S1 on `feat/mvp-s1-inventory-product-fields` (PR open): inventory responses carry
  `product_name`, `category`, `category_name`, `category_icon`; every Decimal schema field
  serialises as a JSON number via `schemas/types.py`; `GET /api/inventory` hides empty and
  discarded unless `include_inactive=true` or an explicit `status`; `consumption_log` written on
  consume (API and scanner) and on the transition to `discarded`. Frontend types and
  `InventoryList` follow; the products fetch in `page.tsx` stays until S2.

## Active PRs and conflicts
- MVP-S1 PR. Touches `crud/inventory_item.py`, which R1/R2 do not; no expected conflicts.
- Worktree `C:/code/Kyokki-docs` still holds merged `docs/mvp-plan-review-amendments`; removable.
- `HANDOFF.md` stays git-tracked by project practice; do not `git rm` it casually.

## Non-obvious decisions or blockers
- DEC-1 left ml, l and kg out. Before R1, confirm conversion factors with the operator
  (`l→dl×10`, `ml→dl÷100`, `kg→g×1000`) and whether tsp/tbsp ever come from receipts.
- Scanner responses and WebSocket payloads still send quantities as strings (hand-built dicts).
- Inventory crud now returns items re-read with `populate_existing` and eager-loaded product and
  category. Any new path returning `InventoryItemResponse` must go through `get_inventory_item`,
  or the model properties hit an unloaded relationship (`MissingGreenlet`).
- Local `alembic check` must run against a fresh database: the pytest suite drops tables but
  leaves `alembic_version`, so checking the test DB reports every table as missing.
- Local backend tests: 3.12 venv, `docker compose up -d postgres redis`, move root `.env` aside
  (legacy keys, look like real credentials; user should delete them), `KYOKKI_TEST_REQUIRE_DB=1`.
- CRLF: check `git show HEAD:<path>` per file; stage CRLF files with `-c core.autocrlf=false`.
- `mypy backend/app/` strict errors 171 → 176 (Column-typed models); CI step non-blocking.
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy F2 on the homelab and confirm the iPad renders inventory, run the R0 spike.

## Next action
Operator merges the S1 PR. Then MVP-C1 (frontend primitives, ungated) can start, and S2/S3 are
unblocked once C1 lands. R1 waits on the R0 spike, DEC-4, and the DEC-1 conversion follow-up.
