# Handoff
Generated-UTC: 2026-09-13T13:31:06Z
Base-SHA: 6382f349658ac0eace5d7ba42824e6a5d119a061

## Round delta
- PR #23 merged (squash): stack-neutral Claude Code scaffold kit. New `.claude/commands/*`
  resolve tooling from the `claude:commands` table in `CLAUDE.md`; six round commands added.
- `CLAUDE.md` rewritten for Kyokki (two-package command table, layout, conventions).
- Formatter hook was a silent no-op (`$CLAUDE_FILE_PATH` never existed). Replaced by
  `.claude/hooks/format.py`, which reads the event JSON from stdin. Verified firing.
- `settings.json`: merged allow-list (78 rules) plus deny-list (force push, hard reset,
  clean, `gh pr merge`). Skills `debug`/`tdd`/`verify` and templates now tracked; GitNexus removed.
- Local `main` had an unrelated July-2025 prototype history. It was replaced by origin/main;
  the old tree is preserved on `backup/local-main-2026-09-13`.

- MVP-F1 (`fix/mvp-f1-green-ci-secrets`): `stack.env` untracked and ignored, `stack.env.example`
  added, ruff pinned to 0.12.12 in requirements and CI, `ruff format --check` blocking.
  Backend CI's pytest job had never passed; root causes found by running the suite against a
  real Postgres: duplicate `dairy` category from composing `sample_category` with
  `seed_categories`; app engine pool and cached Redis client reused across per-test event
  loops (now disposed by an autouse fixture); `requires_ollama` tests not deselected; a real
  bug in `POST /api/shopping/` (`extra={"name": ...}` raises KeyError in logging). Local
  result: 247 passed, 2 skipped, 12 deselected. `KYOKKI_TEST_REQUIRE_DB=1` makes the DB
  fixture fail loudly instead of skipping; CI sets it.
- Local repro recipe: `py -3.12 -m venv backend/.venv`, install requirements, `docker compose
  up -d postgres redis`, run pytest with `POSTGRES_SERVER=localhost` etc. The local `.env`
  holds legacy keys (`gemini_api_key`, `db_password`, `database_url`, `ollama_host`) that the
  strict `Settings` rejects, so move `.env` aside for the run. Those keys look like real
  credentials from the old prototype and should be deleted from `.env`.
- `docs/PLAN_REVIEW_2026-09-13.md` appeared untracked during the F1 session (not authored by
  it). It reviews the MVP plan and recommends amendments; read it before planning Wave 2.

## Active PRs and conflicts
- No open PRs.
- `chore/claude-scaffold-kit` is merged but still exists locally and on origin; safe to delete.
- Local branch `frontend` tracks the old prototype `origin/frontend`; unrelated to current main.

## Non-obvious decisions or blockers
- `docs/TODO.md` still lists Increment 1.7 (main page integration) as open; PR #22 delivered
  it. Mark done before planning from the TODO.
- Round commands expect `docs/backlog.md` and `docs/conventions.md`; neither exists. Everyday
  commands fall back to `docs/TODO.md` per `CLAUDE.md` "Work tracking". Adopting the round
  workflow (step 4 of the kit rollout) was deliberately deferred.
- Hook runs `python -m ruff` (ruff is not on PATH here) and ESLint only when
  `frontend/node_modules/.bin` exists. Hook exit is always 0; failures are silent by design.
- `HANDOFF.md` is git-tracked in this repo, unlike the kit's advice to ignore it. Left tracked
  to match existing project practice; change only with a deliberate `git rm --cached`.
- `local.env` and `git-cheat-sheet.md` sit untracked and unignored at repo root. Check
  `local.env` for secrets before any broad `git add`.
- Carried over: backend DB tests need Postgres and Redis up (`docker compose up -d postgres
  redis`); `InventoryList` takes an optional `productNames` map because `InventoryItem` has
  no product name.

## Next action
MVP-F1 is in flight on `fix/mvp-f1-green-ci-secrets`. Once its PR is merged, two steps are
operator-only (force push is deny-listed for the agent). Do them in this order.

1. Rotate on the homelab, before anything else: new password for `kyokki_user`
   (`ALTER USER kyokki_user PASSWORD '...'`), new key on the LLM endpoint if it enforces one,
   update the homelab's `stack.env`, restart the prod stack.
2. Purge `stack.env` from history (it has been public since commit 0509841, 2026-03-31):
   ```bash
   py -3.12 -m pip install git-filter-repo
   git clone --mirror https://github.com/TKontu/kyokki.git kyokki-purge.git
   cd kyokki-purge.git
   git filter-repo --invert-paths --path stack.env
   git push --force --mirror https://github.com/TKontu/kyokki.git
   ```
   Then re-clone the working repository. Delete or archive local branches that still carry
   the old blobs (`backup/local-main-2026-09-13`, `chore/claude-scaffold-kit`, `frontend`).
   Verify on the fresh clone: `git log --all --oneline -- stack.env` prints nothing.
3. Then MVP-F2 (parametrized prod compose, `docs/DEPLOY.md`, iPad loads inventory).
