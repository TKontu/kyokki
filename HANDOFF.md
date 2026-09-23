# Handoff
Generated-UTC: 2026-09-23T13:50:00Z
Base-SHA: aaf473d6a02373cef1736bbc404a23baee1e1a3f

## Round delta

One increment on `feat/h45-status-surface`: **H45, the display says when it is out of touch.**

- **One banner above every screen** (`components/layout/StatusBanner.tsx` in `AppShell`),
  silent unless something is wrong. In priority: **actions that failed**, each with Retry and
  Dismiss; **not reaching the kitchen server**, with what is on screen dated and a Try again;
  **last updated N minutes ago**, once nothing has landed for 90 s.
- **`useBackendStatus`** derives that from the queries the open page already runs — no polling
  of its own. A 404 is not "unreachable"; a network failure, a 5xx or being offline is.
- **`useFailedActions`** reads the mutation cache, so no call site has to remember it. Retry
  re-runs the same mutation with the same variables and the row clears when it lands. Every
  inventory mutation now carries `meta: { label }`, which is what the banner calls it.
- **The list stops blanking itself**: `InventoryList` shows its error only when there is no
  stock to show; otherwise the banner carries the staleness.
- **Sheet focus lands on `[data-primary]`** — the safe control in a destructive confirm — and
  falls back when that is disabled. **Empty-stock copy** names + Add, Telegram and Scan.

Before this: #82 the Gone screen, #81 one-tap consume and the general Undo, #80 H46.

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
- **Two alerts can be on screen at once** now — the banner and an error toast — so a test that
  wants one should assert on its text, not on `role="alert"`.
- **The homelab is mid-upgrade**: three migrations are queued (`e4b9a7c2d815`, `f6c2d8e1a947`,
  `a3f7b21c6d40`), all rehearsed against seeded rows. The operator intends a redeploy with
  fresh databases.
- **The banner does not speak for the receipt worker or the LLM gateway.** `ReceiptsBanner`
  still carries the pipeline, and H34's timeouts are what would make a gateway state honest.
- **DEC-5** gates H31, the last agent-track prerequisite. **DEC-6** (Next.js), **DEC-7**
  (scanner), **DEC-8** (retention) and **DEC-9** (categories, gating H22) are open.

## Next action

Operator: three of the five MVP-P3 receipts remain, plus the redeploy. On the iPad, the thing to
judge is whether 90 s is the right silence before "last updated" appears.

Code: land this branch once CI is green. Then **H25** — `ItemEditSheet` diffs against the live
item (`app/page.tsx` feeds it the cached one), so a quantity that changes while the sheet is
open is silently re-raised on Save; the one-tap round made that easier to hit. Then H47
(Telegram hygiene, 1h).
