# CLAUDE.md

## What this project is

Kyokki is a self-hosted kitchen inventory system that reduces food waste. Receipt scanning
(OCR + LLM extraction) is the primary input, an always-on iPad PWA is the primary UI, and
everything runs local-first on a homelab. See `docs/ARCHITECTURE.md` for the full design.

**Stack:** Python 3.12, FastAPI, async SQLAlchemy + asyncpg, Alembic, PostgreSQL, Redis
(WebSocket pub/sub, Celery) · Next.js 14 App Router, TypeScript, Tailwind, TanStack Query,
Jest + React Testing Library · Docker Compose for services.
**Profiles:** `.claude/templates/profiles/python-fastapi.md` and `node-typescript.md` hold the
detailed style and pattern guidance. Read them on demand; they are not loaded here.

## Project Commands

Two packages live in one repo. Unsuffixed keys run both; `-backend` / `-frontend` keys run one.
For `test-one`, use the suffixed key that matches the argument's top-level directory. Run
everything from the repo root. Backend tools go through `python -m` so no activated venv is needed.

<!-- claude:commands -->
| Key                | Command |
| ------------------ | ------- |
| install            | pip install -r backend/requirements.txt && (cd frontend && npm ci) |
| test               | (cd backend && python -m pytest) && (cd frontend && npm test) |
| test-backend       | cd backend && python -m pytest |
| test-frontend      | cd frontend && npm test |
| test-one-backend   | cd backend && python -m pytest {arg} -v --tb=short |
| test-one-frontend  | cd frontend && npx jest {arg} |
| lint               | python -m ruff check backend/ && (cd frontend && npm run lint) |
| lint-fix           | python -m ruff check backend/ --fix && (cd frontend && npm run lint -- --fix) |
| format             | python -m ruff format backend/ |
| typecheck          | python -m mypy backend/app/ && (cd frontend && npx tsc --noEmit) |
| run                | docker compose up |
| run-backend        | cd backend && python -m uvicorn app.main:app --reload --port 8000 |
| run-frontend       | cd frontend && npm run dev |
| build              | cd frontend && npm run build |
<!-- /claude:commands -->

- Backend DB tests need PostgreSQL and Redis: `docker compose up -d postgres redis` first.
  Tests marked `requires_mineru` / `requires_vllm` / `requires_ollama` are excluded by default
  (`backend/pytest.ini`). Set `KYOKKI_TEST_REQUIRE_DB=1` (CI does) to fail instead of skip
  when PostgreSQL is unreachable.
- Migrations run through Docker only, because the `postgres` hostname resolves inside the
  compose network: `docker compose run --rm kyokki-api alembic upgrade head`. See `backend/README.md`.
- CI (`.github/workflows/`) runs ruff, mypy, pytest with coverage, and the frontend lint, tsc,
  jest, and build. Match it locally before opening a PR.

## Repository layout

```
backend/app/
  api/endpoints/   FastAPI routers (categories, inventory, products, receipts, scanner, shopping, ws)
  api/exceptions.py  handle_integrity_errors(): DB constraint errors -> 400/409
  services/        receipt pipeline (ocr, llm_extractor, matching), scanner, OFF, websockets
  crud/            per-model data access on top of crud/base.py
  models/ schemas/ SQLAlchemy models and Pydantic request/response schemas
  core/            config.py (settings), logging.py (get_logger)
  db/ parsers/     session/base, store receipt parsers
backend/alembic/   migrations        backend/tests/   mirrors app/ (api, services, db, models, integration)
frontend/app/      Next.js routes, layout, providers
frontend/components/ ui/ (presentational) and inventory/ (domain)
frontend/hooks/    TanStack Query hooks   frontend/lib/api/  fetch client + typed endpoints
frontend/types/    TS types mirroring backend schemas
docs/              ARCHITECTURE.md, specs, TODO.md and per-area *_TODO.md
```

## Architecture conventions

- **Layering:** endpoint -> service -> crud -> model. Endpoints hold no business logic and never
  touch SQLAlchemy directly; services never import from `app.api`.
- **DB writes** go through `async with handle_integrity_errors():` so constraint violations map
  to 400/409 instead of 500.
- **Configuration:** `settings` from `app/core/config.py` (pydantic-settings, reads `.env`).
  Never hardcode hosts, keys, or model names. `.env*`, `stack.env` and `local.env` are
  git-ignored; commit only the `*.example` files.
- **Logging:** `get_logger(__name__)` from `app/core/logging.py`, structured fields, no prints.
  Never log receipt images, API keys, or full LLM prompts at INFO.
- **Real-time:** inventory and receipt mutations broadcast over Redis pub/sub to WebSocket clients
  (`services/websockets.py`, `services/broadcast_helpers.py`). A new mutating endpoint must broadcast too.
- **External services** (MinerU OCR, vLLM/Ollama, Open Food Facts) are wrapped in `app/services`
  with their own exception types and must fail gracefully; the receipt pipeline has fallbacks.
- **Frontend:** all HTTP goes through `lib/api/client.ts`; components get data only via hooks in
  `hooks/`; `types/` must stay in sync with backend `schemas/`. Import with the `@/` alias.

## Testing

- Every behaviour change lands with a test. See the `tdd` skill for the cycle.
- **Backend:** `tests/<layer>/test_*.py` mirroring `app/`. Shared fixtures in `tests/conftest.py`
  (httpx `AsyncClient` over `ASGITransport`, async session). `asyncio_mode = auto`. Markers:
  `unit`, `integration`, `slow`, `requires_db`, `requires_redis`, `requires_mineru`,
  `requires_vllm`, `requires_ollama` (strict markers, so declare new ones in `pytest.ini`).
- **Frontend:** `__tests__/` beside the code under test, Jest + RTL, `jest.setup.js` loads jest-dom.
- Do not weaken, skip, or delete a failing test to make a change land. Fix the change, or say
  explicitly that the test was wrong and why.

## Definition of done

- [ ] Tests written and passing (`test-backend` / `test-frontend`)
- [ ] `lint` clean, `format` applied
- [ ] `typecheck` clean
- [ ] New env vars documented in `.env.example`; migrations included for model changes
- [ ] No secrets, credentials, or personal data added
- [ ] `docs/TODO.md` (or the area `*_TODO.md`) and `HANDOFF.md` updated when the plan changed

## Work tracking

Planned work lives in `docs/TODO.md` plus per-area `docs/*_TODO.md`; session state lives in
`HANDOFF.md`. Commands that expect `docs/backlog.md` should use these files instead until a
backlog is bootstrapped with `/takeoff`.

## Pull requests

```markdown
## Summary
What changed and why.

## Changes
- <change and its reason>

## Testing
- <exact commands run, with their actual output>

## Checklist
- [ ] Tests added/updated
- [ ] Lint/format/typecheck clean
- [ ] Breaking changes and new env vars documented
```
