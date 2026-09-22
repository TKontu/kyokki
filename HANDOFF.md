# Handoff
Generated-UTC: 2026-09-22T19:35:00Z
Base-SHA: 14cd53b75b8a2af4b38896f956fa4487e31deea1

## Round delta

One increment on `feat/gone-screen`: **waste is visible, and kept.**

- **`/gone`**, a fifth destination in the rail: what was thrown away or finished, newest first,
  grouped by day, with the amount. 30 days by default; 7-day and All filters.
- **A summary header** from `GET /api/consumption-log/summary` — events and totals per unit
  (grams and pieces are kept apart). One `GROUP BY`; the seam post-MVP 8's metrics will read.
- **"Put it back"** on any row whose item is still in the bin. The first screen that reaches
  `restore` without catching the header's Undo in time; rows carry `item_status` to say so.
- **The record outlives the item** (operator ruling): `consumption_log.inventory_item_id` is
  `ON DELETE SET NULL`, not `CASCADE`, and the row carries its own `unit`. Deleting an item no
  longer takes its waste with it, so metrics cover everything ever thrown away. Migration
  `a3f7b21c6d40`. The delete confirm says so.
- **Undo steps over a batch whose item was deleted** instead of refusing forever.

Before this: H46 (#80) gave the log a read path, and #81 made consuming one tap with one
general Undo.

## Active PRs and conflicts

This branch's PR, if opened. Not visible from PR metadata: **`HANDOFF.md` is tracked here, not
gitignored** — the last PR of each wave owns it together with `docs/TODO.md`.

## Non-obvious decisions or blockers

- **The Linux dev container runs the whole suite.** PostgreSQL 16 and Redis are installed in it
  (`sudo service postgresql start`, `sudo service redis-server start`; role and database
  `kyokki`/`kyokki`). Pass settings as env vars — the repo-root `.env` belongs to the Windows
  setup: `POSTGRES_SERVER=localhost POSTGRES_USER=kyokki POSTGRES_PASSWORD=kyokki
  POSTGRES_DB=kyokki REDIS_HOST=localhost KYOKKI_TEST_REQUIRE_DB=1`. `alembic upgrade head` and
  `check` work against the same database. The Windows workstation still has no Docker.
- **The share is mounted without exec** (`file_mode=0664`): backend tools run as
  `backend/.venv/bin/python -m …` (its `bin/ruff` links to `~/.local/share/kyokki-tools`),
  frontend tools as `node node_modules/<pkg>/…`. `next build` cannot write
  `frontend/.next/cache` (left by Windows); build from a copy outside the share.
- **Mixed line endings** (H44 open): about a third of the files are CRLF. Edit them without
  converting, or the diff becomes the whole file.
- **PR titles take no scope**: `feat:`, not `feat(products):`.
- **The homelab is mid-upgrade**: it serves Q8 and Q11 but not Q12 onward. The operator intends
  a full redeploy with **fresh databases**; three migrations are queued (`e4b9a7c2d815`,
  `f6c2d8e1a947`, `a3f7b21c6d40`), all rehearsed against seeded rows.
- **Undo reaches only what the log records.** Adding stock, deleting an item and date or shelf
  edits without a quantity change are not steps. Pre-`f6c2d8e1a947` rows stop the walk back.
- **Waste has no rate or trend yet**, only totals per window. The summary endpoint is the shape
  those need.
- **DEC-5** gates H31, the last agent-track prerequisite. **DEC-9** gates H22, whose FK rules
  this round settled one of. **DEC-6** (Next.js), **DEC-7** (scanner) and **DEC-8** (retention)
  are still open.

## Next action

Operator: try Gone on the iPad — whether 30 days is the right default, and whether "Put it
back" belongs there. Three of the five MVP-P3 receipts remain, plus the redeploy.

Code: land this branch once CI is green. Then **H45** (a status surface: last sync, backend
unreachable, failed actions with a retry chip) — it is the most valuable unblocked row now that
a card tap is silent on success, and a stale list looks exactly like a fresh one. H47 (Telegram
hygiene, 1h) is the small one, and H25 (the edit sheet diffs against a live item, so a Save can
silently re-raise a quantity that changed underneath it) is a real bug still open.
