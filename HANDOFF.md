# Handoff
Generated-UTC: 2026-09-20T11:05:00Z
Base-SHA: 33541a96ccb2342150446eb563748feb76cba943

## Round delta

Four increments (#75–#78). The write paths and then the screen.

- **#75 H23** — one status machine (`services/item_status.py`) and row locks on consume and
  correction. Fixed a real lost update: two taps both read 4 and both wrote 3, losing one
  helping while both log rows landed. Also: discard freezes the item, a correction above full
  stops reading `partial`, create refuses `current > initial`.
- **#76 H24** — eight `StrEnum` vocabularies; the create path used to take any string where
  PATCH answered 422. `scripts.check_vocabularies` runs in CI against `frontend/types/`.
- **#77** — **Undo** on the *Mark as gone* toast, using H23's `restore`.
- **#78** — expired items get their own section with a real age, plus
  `POST /api/inventory/discard` and `/restore` (ids in, counters out, one transaction).

New: `contracts/status-transitions.json` (read by both test suites), `check_vocabularies`; mypy **153 → 150**.

## Active PRs and conflicts

None open. Not visible from PR metadata: **`HANDOFF.md` is tracked here, not gitignored** — the
last PR of each wave owns it together with `docs/TODO.md`, so two waves in flight will conflict
on both.

## Non-obvious decisions or blockers

- **No Docker on this workstation** (operator ruling, 2026-09-19). DB-backed tests, migration
  rehearsals and `alembic check` run in **CI only**; it has caught three failures this month that
  local runs could not. Locally: `pytest -m "not requires_db and not requires_mineru and not
  requires_vllm and not requires_ollama"` (421 tests) — and `POSTGRES_*`/`REDIS_HOST` must still
  be set to *something*, because `Settings` declares them required.
- **PR titles take no scope**: `feat:`, not `feat(products):`. CI rejects the latter and only
  re-checks the title on an `edited` event.
- **The homelab is mid-upgrade**: it serves Q8 and Q11 but not Q12 onward. The operator intends a
  full redeploy with **fresh databases**, so migration backfills need no rescue path — and DB
  `CHECK` constraints were deliberately deferred until after that wipe.
- **`restore` has no screen.** Nothing lists inactive items, so the Undo toast window is the only
  way back from *Mark as gone*.
- **Nothing reads `consumption_log` back.** Every discard writes a waste row and always has;
  there is no router. Waste is recorded and invisible.
- **DEC-5** gates H31, the last agent-track prerequisite. **DEC-9** gates H22.

## Next action

Operator: three of the five MVP-P3 receipts remain, plus the redeploy.

Code: **H46 — give the waste log a read path.** Schemas exist and no router touches them; start at
`backend/app/schemas/consumption_log.py` and the H46 row in `docs/TODO.md`.
