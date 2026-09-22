# Handoff
Generated-UTC: 2026-09-22T16:55:00Z
Base-SHA: 5089f138142d68bb0cffc5a6b04c840a7a742438

## Round delta

One increment from the operator's trial, on `feat/one-tap-consume-and-undo`: **consuming is
one tap, and there is one general undo.**

- Stock cards consume directly: a big step button (−1 piece, or −¼ of a measured pack, meant
  to be pressed repeatedly), a smaller **All n / Done**, and **…** for the sheet with every
  other amount plus **Edit item**. A card tap raises no success toast.
- The header has **↶ Undo**, which always names what it would reverse and steps further back
  on each press: consume, finish, mark as gone, a cleared shelf (one step), a restore, a
  correction. `GET`/`POST /api/inventory/undo`, `services/undo.py`.
- Each consumption-log row now keeps `previous` (the item before the event) and a `batch_id`;
  undo restores `previous` and deletes the rows. Migration `f6c2d8e1a947`.
- The toast Undos (#77 Mark as gone, #78 cleared shelf) and `useRestoreInventoryItem` are gone.
  Post-MVP 12 (undo for consume) is closed by this.

H46 (PR #80) merged just before this, and `consumed_at` is now written.

## Active PRs and conflicts

This branch's PR, if opened. Not visible from PR metadata: **`HANDOFF.md` is tracked here, not
gitignored** — the last PR of each wave owns it together with `docs/TODO.md`, so two waves in
flight will conflict on both.

## Non-obvious decisions or blockers

- **The Linux dev container can run the whole suite now.** PostgreSQL 16 and Redis run inside
  the container (`sudo service postgresql start`, `sudo service redis-server start`; role and
  database `kyokki`/`kyokki`). Pass the settings as env vars, not in the repo-root `.env` —
  that file belongs to the Windows setup: `POSTGRES_SERVER=localhost POSTGRES_USER=kyokki
  POSTGRES_PASSWORD=kyokki POSTGRES_DB=kyokki REDIS_HOST=localhost KYOKKI_TEST_REQUIRE_DB=1`.
  `alembic upgrade head` / `check` work against the same database. The Windows workstation
  still has no Docker, and CI is still the authority.
- **The share is mounted without exec** (`file_mode=0664`): run backend tools as
  `backend/.venv/bin/python -m …` (its `bin/ruff` links to `~/.local/share/kyokki-tools`), and
  frontend tools as `node node_modules/<pkg>/…` — `node_modules/.bin` will not run. `next build`
  cannot write `frontend/.next/cache` (left by Windows); build from a copy outside the share.
- **Mixed line endings** (H44 is open): about a third of the files are CRLF. Edit them without
  converting, or the diff becomes the whole file.
- **PR titles take no scope**: `feat:`, not `feat(products):`.
- **The homelab is mid-upgrade**: it serves Q8 and Q11 but not Q12 onward. The operator intends a
  full redeploy with **fresh databases**; migration backfills need no rescue path.
- **Undo reaches only what the log records.** Adding stock, deleting an item and date or shelf
  edits without a quantity change are not steps. Rows from before `f6c2d8e1a947` have no
  `previous` and stop the walk back.
- **`restore` still has no list screen**, but the header Undo now covers the mis-tap case that
  made it urgent. A "gone" list still waits on the operator's question: how long a binned item
  stays visible.
- **DEC-5** gates H31, the last agent-track prerequisite. **DEC-9** gates H22.

## Next action

Operator: try one-tap consume and Undo on the iPad; three of the five MVP-P3 receipts remain,
plus the redeploy.

Code: land this branch once CI is green. Then H47 (Telegram hygiene, 1h), the smallest open H
row with no decision attached, unless the trial turns up more friction first.
