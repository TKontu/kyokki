# Handoff
Generated-UTC: 2026-09-22T15:30:00Z
Base-SHA: 3b169770cfa321f2535d9273c79fcef48ba1e139

## Round delta

One increment: **H46**, the consumption history, on `feat/h46-consumption-history`.

- Every quantity event writes one row: `use_partial | use_full | discard | restore | correct`
  (`adjust` is gone). Each row carries `quantity_after`, so a run of rows replays the item.
  Corrections and restores were unlogged until now; a discard of an already-empty item logged 0
  and now logs nothing.
- `consumed_at` is written: stamped when an item goes empty or in the bin, cleared when it comes
  back.
- `GET /api/consumption-log`: paged, newest first, filters by action (repeatable), product, item
  and a `since`/`until` window. Waste is `?action=discard`.
- Dropped as dead (operator, 2026-09-22): `consumption_log.consumption_context` and
  `category.meal_contexts`. Post-MVP item 8 says how they come back.
- Frontend: types, API module and `useConsumptionLog` only — **no screen**. The API client now
  repeats a key for an array param and no longer sends a bare `?`.

New: migration `e4b9a7c2d815` (backfills `quantity_after`), `ConsumptionAction` in
`check_vocabularies`; mypy **150 → 149**.

## Active PRs and conflicts

H46's PR, if opened. Not visible from PR metadata: **`HANDOFF.md` is tracked here, not
gitignored** — the last PR of each wave owns it together with `docs/TODO.md`, so two waves in
flight will conflict on both.

## Non-obvious decisions or blockers

- **No Docker on this workstation** (operator ruling, 2026-09-19). DB-backed tests, migration
  rehearsals and `alembic check` run in **CI only**. H46's DB tests and its migration have
  **not run anywhere yet** — CI is their first run. Locally: `pytest -m "not requires_db and
  not requires_mineru and not requires_vllm and not requires_ollama"` — and `POSTGRES_*`
  (`POSTGRES_SERVER`, not `_HOST`) and `REDIS_HOST` must still be set to *something*.
- **The Linux dev container** works off a CIFS share mounted `file_mode=0664`: nothing on it is
  executable. `backend/.venv` is a symlinked venv (run tools as `python -m …`); its `bin/ruff`
  links to `~/.local/share/kyokki-tools`. In `frontend/`, call `node node_modules/<pkg>/…`
  directly: `node_modules/.bin` will not run. `core.fileMode=false` hides the mode noise.
- **PR titles take no scope**: `feat:`, not `feat(products):`. CI rejects the latter and only
  re-checks the title on an `edited` event.
- **The homelab is mid-upgrade**: it serves Q8 and Q11 but not Q12 onward. The operator intends a
  full redeploy with **fresh databases**, so migration backfills need no rescue path — and DB
  `CHECK` constraints were deliberately deferred until after that wipe.
- **`restore` still has no screen**, and waste is still invisible on the iPad. Both need the same
  list of gone items, which runs into the question the operator set aside on 2026-09-20: how long
  something stays visible after it is binned. `consumed_at` is now the column that answers it.
- **Deleting an item deletes its history** (FK `CASCADE`, and the sheet says so). H22 owns the
  FK rules if that should change.
- **DEC-5** gates H31, the last agent-track prerequisite. **DEC-9** gates H22.

## Next action

Operator: three of the five MVP-P3 receipts remain, plus the redeploy. Decide whether a
"gone" list (waste plus Put it back) is wanted, and for how long a binned item stays on it.

Code: land H46 once CI is green. Then either that screen, on `useConsumptionLog` and
`consumed_at`, if the operator wants it, or H47 (Telegram hygiene, 1h), the smallest open H row
with no decision attached.
