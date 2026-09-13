# Handoff
Generated-UTC: 2026-09-13T18:45:00Z
Base-SHA: 83b2e62

## Round delta
- PR #24 merged (MVP-F1): `stack.env` untracked and ignored, `stack.env.example` added, ruff
  pinned, backend CI green for the first time (fixture collision, engine/Redis clients leaking
  across pytest-asyncio loops, `requires_ollama` deselected, real 500 in `POST /api/shopping/`
  from `extra={"name": ...}`). Details in the PR description.
- MVP-F2 in flight on `feat/mvp-f2-deployable-stack`: same-origin `/api` rewrite in
  `next.config.mjs` (`API_INTERNAL_URL` build arg, default `http://kyokki-api:8000`), client
  default base URL `/api`; `celery-worker` removed from both compose files and `celery_app.py`
  deleted (it referenced a non-existent `app.tasks` and crash-looped); Postgres/Redis host ports
  unpublished in prod; migration `7c1f2a9d4b30` adds the missing unique constraint and CI runs
  `alembic check`; `python -m app.db.seed_categories` entry point; `docs/DEPLOY.md` runbook.
- `docs/PLAN_REVIEW_2026-09-13.md` (untracked, user-authored) reviews the MVP plan. Its F2
  amendments were adopted; the rest (R0 spike, alias learning, unit/serialisation decisions)
  are pending operator decisions listed in its section 7.

## Active PRs and conflicts
- MVP-F2 PR (see git log / `gh pr list`). No other open PRs.
- `chore/claude-scaffold-kit` and `fix/mvp-f1-green-ci-secrets` are merged; safe to delete.

## Non-obvious decisions or blockers
- Local backend tests: Python 3.12 venv at `backend/.venv`, `docker compose up -d postgres
  redis`, env vars `POSTGRES_SERVER=localhost ... KYOKKI_TEST_REQUIRE_DB=1`, and move the root
  `.env` aside first: it still carries legacy prototype keys (`gemini_api_key`, `db_password`,
  `database_url`, `ollama_host`) that the strict `Settings` rejects. Those look like real
  credentials and should be deleted from `.env`.
- Many committed backend files are CRLF in git while docs are LF. Preserve the existing ending
  and stage CRLF files with `git -c core.autocrlf=false add`, or the diff becomes the whole file.
- `mypy backend/app/` has 171 strict-mode errors; the CI step is `continue-on-error`. Post-MVP debt.
- `git pull` of the F1 merge deletes a checkout's tracked `stack.env` (happened locally;
  restored with `git show 6382f34:stack.env > stack.env`). The homelab checkout will hit the
  same thing: back the file up before pulling. Documented in `docs/DEPLOY.md`.
- Quantities are JSON strings on the wire (`"1000.00"`); the inventory page crashed on the
  first real item. Frontend now coerces at the API boundary (`normalizeInventoryItem`). The
  wire-format decision (review DEC 2) is still open for MVP-S1.
- `ALLOWED_ORIGINS` as a comma-separated env value crashed `Settings` at import (pydantic-
  settings decodes `list[str]` env values as JSON first). Fixed with `NoDecode`; the prod API
  had not been startable that way since PR #21. Caught only by running the prod compose file.
- `app/db/base.py` claimed to import all models and imported none, so Alembic autogenerate saw
  an empty schema. Fixed in F2 with `tests/db/test_metadata_registry.py` guarding it.
- Next.js standalone output inlines `next.config.mjs` at build time, so the rewrite destination
  is fixed per image. It is the compose service name, so this is fine; do not try to make it a
  runtime env var without switching off standalone output.

## Next action
1. **Operator, after the F2 PR merges:** on the homelab, back up `stack.env`, `git pull`
   (restore `stack.env` if the pull removed it), `docker compose -f
   docker-compose.prod.yml up -d --build`, `... run --rm kyokki-api alembic upgrade head`,
   `... run --rm kyokki-api python -m app.db.seed_categories`, then open `http://<host>:17301`
   on the iPad. Report back; that ticks MVP-F2. `ALLOWED_ORIGINS` may be removed from `stack.env`.
2. **Operator, still outstanding from F1:** rotate the Postgres password and LLM key, then purge
   `stack.env` from history (runbook in PR #24's description).
3. **Decisions before Wave 2** (from `docs/PLAN_REVIEW_2026-09-13.md` section 7): unit
   vocabulary (`ml|g|pcs` recommended), JSON numbers vs strings for quantities (numbers
   recommended), and the fallback order if the LLM spike (proposed MVP-R0) fails.
4. Then Wave 2: backend MVP-S1, MVP-R1, MVP-R2 in parallel with frontend MVP-C1, MVP-C2.
