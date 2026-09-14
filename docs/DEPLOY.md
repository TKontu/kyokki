# Deploying Kyokki on the homelab

This is the runbook for the production Docker Compose stack (`docker-compose.prod.yml`).
Follow it top to bottom on a fresh host; the "Updating" section covers later releases.

## What you get

| Port  | Service  | Purpose |
| ----- | -------- | ------- |
| 17301 | frontend | The iPad opens `http://<host>:17301`. `/api/*` is proxied to the backend on the same origin, so no CORS setup is needed. |
| 17300 | backend  | FastAPI directly (`/api/health`, diagnostics, future integrations such as Home Assistant). |

PostgreSQL and Redis are reachable only inside the compose network. Receipt uploads land in
`./data`, logs in `./logs`, and the database in the `postgres_data` volume.

## Prerequisites

- Docker Engine with the Compose plugin on the homelab host.
- An OpenAI-compatible LLM endpoint reachable from that host (the llama-swap gateway with a
  vision-capable model such as `muse-glimmer`). MinerU OCR is optional: when it is unreachable,
  receipt photos are read directly by the vision model.
  Their URLs go into `stack.env`.
- Git access to the repository.

## First deployment

```bash
git clone https://github.com/TKontu/kyokki.git
cd kyokki

# 1. Configuration. stack.env is git-ignored; never commit it.
cp stack.env.example stack.env
#    Edit stack.env: POSTGRES_PASSWORD, LLM_BASE_URL, LLM_MODEL (and LLM_REASONING_STRENGTH),
#    MINERU_BASE_URL.

# 2. Build and start (first build takes a few minutes: Python deps + Next.js build).
docker compose -f docker-compose.prod.yml up -d --build

# 3. Database schema, then the default categories (idempotent, safe to rerun).
docker compose -f docker-compose.prod.yml run --rm kyokki-api alembic upgrade head
docker compose -f docker-compose.prod.yml run --rm kyokki-api python -m app.db.seed_categories

# 4. Verify.
curl -s http://localhost:17300/api/health      # backend directly
curl -s http://localhost:17301/api/health      # through the frontend proxy
docker compose -f docker-compose.prod.yml ps   # api, frontend, postgres, redis all "Up"
```

`POSTGRES_PASSWORD` in `stack.env` is used both by the `postgres` container (on first start it
creates the database with it) and by the API. Changing it later means changing it in Postgres
too (`ALTER USER kyokki_user PASSWORD '...'`).

## On the iPad

1. Open Safari and go to `http://<host>:17301`. The inventory list should render.
2. Share → **Add to Home Screen**. Launch Kyokki from the icon.
3. Settings → Display & Brightness → Auto-Lock → **Never** (a web app does not keep the
   screen awake by itself). Guided Access is an alternative for a dedicated kitchen iPad.

## Updating

> **First update after 2026-09-13:** `stack.env` used to be tracked in git. The commit that
> untracked it deletes the file from any checkout that still has the old version when you
> `git pull`. Copy it aside first (`cp stack.env /tmp/stack.env.bak`) and restore it after the
> pull. Later updates do not touch it.

> **Unit migration (MVP-U1, revision `a4f8c2d91e37`):** `alembic upgrade head` converts stored
> quantities to `dl | tsp | tbsp | g | pcs` (e.g. 1000 ml becomes 10 dl). It prints a warning for
> rows with units it does not know and leaves them unchanged. Downgrading only turns `dl` back
> into `ml`; take a database backup before upgrading if you might need to roll back.

```bash
cd kyokki
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm kyokki-api alembic upgrade head
```

The frontend image bakes in the backend address (`API_INTERNAL_URL`, the compose service name),
so it only needs rebuilding when the code changes, never when the LAN IP changes.

## Operations

```bash
docker compose -f docker-compose.prod.yml logs -f kyokki-api      # backend logs
docker compose -f docker-compose.prod.yml logs -f frontend        # Next.js logs
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U kyokki_user kyokki > backup-$(date +%F).sql          # database backup
docker compose -f docker-compose.prod.yml down                    # stop (data volumes stay)
```

## Development on a workstation

The dev stack (`docker-compose.yml`) runs only the backend services; the frontend runs on the
host so hot reload works.

```bash
docker compose up -d postgres redis
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev            # http://localhost:3000, /api/* proxied to :8000
```

`next.config.mjs` proxies `/api/*` to `API_INTERNAL_URL` (default `http://localhost:8000`).
Set `NEXT_PUBLIC_API_URL` only if the browser should call the API on another origin; that
also requires `ALLOWED_ORIGINS` on the backend.

## Troubleshooting

- **Frontend shows "Could not load product names" or an empty error state:** check
  `curl http://localhost:17301/api/health`. If that fails but `:17300` works, the frontend
  container cannot reach `kyokki-api`; check `docker compose ... logs frontend`.
- **`alembic upgrade head` fails with "could not translate host name postgres":** it was run
  outside Docker. Always use `docker compose -f docker-compose.prod.yml run --rm kyokki-api ...`.
- **Migrations and models disagree:** CI runs `alembic check`; if you edit a model, add a
  revision with `alembic revision --autogenerate -m "..."` inside the container. New model
  modules must be imported in `app/models/__init__.py`, which `app/db/base.py` re-exports for
  Alembic; otherwise autogenerate cannot see them.
