# Handoff
Generated-UTC: 2026-09-23T19:15:00Z
Base-SHA: 267786212eb7d2e14691c0f8376d44eff63d4ca1

## Round delta

One increment on `feat/h25-one-source-of-truth`: **H25, a sheet shows the truth while it is
open.**

- **`useFieldEdit`** (`hooks/useFieldEdit.ts`): an untouched field follows the record, a touched
  field keeps what the cook typed, and only touched-and-different fields are sent. Save can no
  longer arm itself, and a background change can no longer be written back over the server.
- **A touched field that also moved says so** — "Quantity changed to 2 while this was open",
  with **Keep mine** and **Use 2** (`components/ui/FieldMoved.tsx`).
- Both sheets: `ItemEditSheet` and `ProductEditSheet`. `ItemEditForm` is keyed by item id.
- **Quick add stops guessing**: `unit` is optional on `QuickAddRequest`, and unit and location
  are sent only when the cook chose them; the server falls back to the resolved product's own.
- **"Create new" waits for the search to answer** for the word on screen (`settled` on
  `useProductSearch`) — the debounce window is where duplicate products were made.
- **The consume mirror predicts the opened clock** (Q5): items now carry the product's
  `opened_shelf_life_days` and `avg_piece_grams`, so the expiry badge no longer jumps after a
  tap. `applyConsume` mirrors `_start_opened_clock`, loose produce exempt.

Before this: #83 the status banner, #82 the Gone screen, #81 one-tap consume and Undo, #80 H46.

## Active PRs and conflicts

This branch's PR, if opened. **`HANDOFF.md` is tracked, not gitignored** — the last PR of each
wave owns it together with `docs/TODO.md`.

## Non-obvious decisions or blockers

- **The Linux dev container runs everything.** PostgreSQL 16 and Redis are installed
  (`sudo service postgresql start`, `sudo service redis-server start`; role and database
  `kyokki`/`kyokki`). Settings go in env vars, not the repo-root `.env`, which belongs to the
  Windows setup: `POSTGRES_SERVER=localhost POSTGRES_USER=kyokki POSTGRES_PASSWORD=kyokki
  POSTGRES_DB=kyokki REDIS_HOST=localhost KYOKKI_TEST_REQUIRE_DB=1`.
- **The share is mounted without exec** (`file_mode=0664`): backend tools as
  `backend/.venv/bin/python -m …` (its `bin/ruff` links to `~/.local/share/kyokki-tools`),
  frontend tools as `node node_modules/<pkg>/…`. `next build` cannot write
  `frontend/.next/cache` (left by Windows); build from a copy outside the share.
- **Mixed line endings** (H44 open): about a third of the files are CRLF. Edit them without
  converting, or the diff becomes the whole file.
- **Two alerts can be on screen at once** (the status banner and an error toast), so a test that
  wants one should assert on its text, not on `role="alert"`.
- **No migration this round**, though the API grew: `opened_shelf_life_days` and
  `avg_piece_grams` are read off the loaded product, like `product_name`. Three migrations are
  still queued for the homelab (`e4b9a7c2d815`, `f6c2d8e1a947`, `a3f7b21c6d40`).
- **A quick add may now omit `unit`.** The server takes the resolved product's, and `pcs` only
  when there is nothing to resolve to. Anything else posting to `/quick-add` gets the same
  fallback rather than a 422.
- **DEC-5** gates H31, the last agent-track prerequisite. **DEC-6** (Next.js), **DEC-7**
  (scanner), **DEC-8** (retention) and **DEC-9** (categories, gating H22) are open.

## Next action

Operator: three of the five MVP-P3 receipts remain, plus the redeploy. Worth judging on the
iPad: whether the "changed while this was open" line reads clearly enough to act on.

Code: land this branch once CI is green. Then **H47** (Telegram hygiene, 1h: exit non-zero on
the 409 from a second instance, keep gateway internals out of `failure_text`, document a dev
token) — the smallest open row with no decision attached. H26/H27 (extraction honesty, the
heuristic parser) are the ones to do if the remaining MVP-P3 receipts give trouble.
