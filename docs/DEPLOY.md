# Deploying Kyokki on the homelab

This is the runbook for the production Docker Compose stack (`docker-compose.prod.yml`).
**Nothing is built on the homelab:** every push to `main` publishes two images to GHCR
(`.github/workflows/images.yml`), and the stack pulls them. Deploy it straight from GitHub with
Portainer, or with `docker compose` on the host. The "Updating" section covers later releases.

## What you get

| Port  | Service  | Purpose |
| ----- | -------- | ------- |
| 17301 | frontend | The iPad opens `http://<host>:17301`. `/api/*` is proxied to the backend on the same origin, so no CORS setup is needed. |
| 17300 | backend  | FastAPI directly (`/api/health`, diagnostics, future integrations such as Home Assistant). |

PostgreSQL and Redis are reachable only inside the compose network. Receipt uploads land in
the named volume `kyokki_data`, logs in `kyokki_logs`, and the database in `postgres_data`.
(The dev stack in `docker-compose.yml` is the one that bind-mounts `./data` and `./logs`.)

Two more services publish no port:
- **`kyokki-worker`** reads uploaded receipts (OCR or vision, LLM extraction, matching) one at a
  time from a queue in Postgres. Uploads return immediately with status `queued`; the receipt
  moves to `processing` and then `completed` or `failed`. Without the worker, receipts stay
  queued.
- **`kyokki-telegram`** is the receipt drop-in bot (see "Telegram bot" below).

## Prerequisites

- Docker Engine with the Compose plugin on the homelab host (Portainer optional but assumed
  below).
- The two packages public, once: GitHub → your profile → **Packages** → `kyokki-backend`, then
  `kyokki-frontend` → *Package settings* → *Change visibility* → **Public**. Private packages
  would need a registry login on the host instead.
- An OpenAI-compatible LLM endpoint reachable from that host (the llama-swap gateway with a
  vision-capable model such as `muse-glimmer`). Name the copy pinned to the GPU Kyokki may use
  (the gateway lists `c0.*` and `c2.*` copies; Kyokki defaults to `c2.muse-glimmer`).
  MinerU OCR is optional: when it is unreachable,
  receipt photos are read directly by the vision model.
  Their URLs go into `stack.env`.
- Git access to the repository (public, so no credentials needed).
- **An iPad (or any browser) on iPadOS 15 or newer.** Measured 2026-09-17: the app is a blank
  page on Safari 12 (iPadOS 12.5, e.g. a 1st-gen iPad Air, which cannot be updated further).
  The shipped bundle uses `?.`, `??` and `:is()`, and Next 14's App Router compiles to a fixed
  modern target that ignores `browserslist` - setting `safari >= 12` and rebuilding produced
  byte-identical chunks. TanStack Query v5 also publishes Safari 15 as its floor. An iPad 7th
  gen or newer is comfortably inside this.

## First deployment with Portainer (from GitHub)

1. **Stacks → Add stack → Repository.**
   - Repository URL: `https://github.com/TKontu/kyokki`
   - Reference: `refs/heads/main`
   - Compose path: `docker-compose.prod.yml`
   - *Automatic updates* are optional; see "Updating".
2. **Environment variables.** Open *Advanced mode* and paste the contents of
   `stack.env.example`, then fill in `POSTGRES_PASSWORD` (and `TELEGRAM_BOT_TOKEN` if you have
   a bot). Every other key already carries the value this homelab uses.
3. **Deploy the stack.** Portainer pulls the two GHCR images, starts Postgres, waits for it to
   be healthy, runs `kyokki-migrate` (schema + default categories, both idempotent) and only
   then starts the API, worker, Telegram bot and frontend.
4. **Verify.**
   - `http://<host>:17300/api/health` answers `{"status":"ok","postgres":"ok","redis":"ok"}`.
     It is a readiness check: 503 with `"status":"degraded"` names the dependency that is down.
     `http://<host>:17301/api/health` is the same thing through the frontend proxy, which is
     what the iPad uses, so check that one too.
     (`/api/health/live` only says the process is up; it is what the container healthcheck
     polls, so a slow database never restart-loops the API.)
   - In Portainer the stack shows `kyokki-migrate` **Exited (0)** and the other five services
     **running**. That exit is expected: it is a one-shot job.

`POSTGRES_PASSWORD` is used both by the `postgres` container (on first start it creates the
database with it) and by the API. Changing it later means changing it in Postgres too
(`ALTER USER kyokki_user PASSWORD '...'`).

### Or with docker compose on the host

```bash
git clone https://github.com/TKontu/kyokki.git
cd kyokki
cp stack.env.example stack.env      # fill in POSTGRES_PASSWORD; stack.env is git-ignored
docker compose --env-file stack.env -f docker-compose.prod.yml --env-file stack.env up -d
docker compose --env-file stack.env -f docker-compose.prod.yml --env-file stack.env ps
```

To build the images locally instead of pulling them, add the build override:

```bash
docker compose --env-file stack.env -f docker-compose.prod.yml -f docker-compose.build.yml --env-file stack.env up -d --build
```

## On the iPad

1. Open Safari and go to `http://<host>:17301`. The inventory list should render.
2. Share → **Add to Home Screen**. Launch Kyokki from the icon: it opens full screen with no
   browser chrome, using the web app manifest plus the `apple-mobile-web-app-*` metadata
   (MVP-P2). The Home Screen icon is the Kyokki fridge mark.
3. Settings → Display & Brightness → Auto-Lock → **Never** (a web app does not keep the
   screen awake by itself). Guided Access is an alternative for a dedicated kitchen iPad.
4. The stock list refreshes itself every 30 seconds, so a wall-mounted iPad nobody touches
   still shows what is actually in the fridge. Receipts being read refresh every 3 seconds.
5. **Appearance follows the iPad.** Settings → Display & Brightness → Dark (or Automatic, which
   switches at sunset) turns the app dark, so the kitchen screen is not white at midnight.

Two honest limits:

- The manifest asks for landscape, but **iOS ignores `orientation` for home-screen web apps**.
  The wall mount decides the orientation.
- **No offline mode**, and not only by choice: the stack is served over plain HTTP on the LAN,
  which is not a secure context, so a service worker cannot register at all. Post-MVP, TLS
  would have to come first.

## Updating

> **First update after 2026-09-13:** `stack.env` used to be tracked in git. The commit that
> untracked it deletes the file from any checkout that still has the old version when you
> `git pull`. Copy it aside first (`cp stack.env /tmp/stack.env.bak`) and restore it after the
> pull. Later updates do not touch it.

> **Item history on delete (MVP-S4, revision `d5f1b8c2e4a6`):** deleting an inventory item now
> also deletes its consumption history (it is meant for items entered by mistake). Use
> "Mark as gone" on the iPad for things that were thrown away; that keeps the history.

> **Receipt queue (MVP-R3, revision `c3e9a7b5d1f2`):** the migration adds `queued_at`,
> `processing_started_at` and `error` to receipts, and the new `kyokki-worker` service reads the
> queue; `up -d --build` starts it. Receipts uploaded before this release keep status `uploaded`;
> queue one with `curl -X POST http://localhost:17300/api/receipts/<id>/process`. A receipt
> left `processing` for more than `RECEIPT_STALE_MINUTES` (default 10), for example after the
> worker was restarted mid-read, is shown as `failed` and can be queued again the same way.

> **Unit migration (MVP-U1, revision `a4f8c2d91e37`):** `alembic upgrade head` converts stored
> quantities to `dl | tsp | tbsp | g | pcs` (e.g. 1000 ml becomes 10 dl). It prints a warning for
> rows with units it does not know and leaves them unchanged. Downgrading only turns `dl` back
> into `ml`; take a database backup before upgrading if you might need to roll back.

**Portainer:** open the stack → **Pull and redeploy** (tick *re-pull image*). That fetches the
newest `latest` images and re-runs `kyokki-migrate`, so the schema is migrated before the
services come back. Portainer's *Automatic updates* (polling or webhook) does the same on a
schedule.

**On the host:**

```bash
cd kyokki
git pull
docker compose --env-file stack.env -f docker-compose.prod.yml --env-file stack.env pull
docker compose --env-file stack.env -f docker-compose.prod.yml --env-file stack.env up -d
```

Migrations are no longer a separate step: `kyokki-migrate` runs `alembic upgrade head` and the
category seed on every deploy.

To roll back, set `KYOKKI_BACKEND_IMAGE` and `KYOKKI_FRONTEND_IMAGE` to a `sha-<commit>` tag
(every build publishes one alongside `latest`) and redeploy.

The frontend image bakes in the backend address (`API_INTERNAL_URL`, the compose service name),
so it never needs rebuilding when the LAN IP changes.

## Telegram bot

Share receipts to a private Telegram bot from the phone: order PDFs, S-Group and K-Plussa app
receipts or screenshots, and photos of paper receipts. The `kyokki-telegram` service reads each
one and replies with a summary, for example
`S-group, 2.1.2026: 49 items, 3 matched. New: … (+37). Review on the iPad.`
It long-polls Telegram, so the homelab needs no open port.

1. In Telegram, open **@BotFather**, send `/newbot` and pick a name. Copy the token.
2. Put it in `stack.env` as `TELEGRAM_BOT_TOKEN=...` and start the stack:
   `docker compose --env-file stack.env -f docker-compose.prod.yml up -d`.
   (No `--build`: `docker-compose.prod.yml` pulls published images and has no
   `build:` section. To build locally, add `-f docker-compose.build.yml`.)
3. Send `/start` to the bot. It answers "This bot is private. Your chat id is …".
4. Add that id to `TELEGRAM_ALLOWED_CHAT_IDS` in `stack.env` (comma-separated for several
   people) and restart the bot:
   `docker compose --env-file stack.env -f docker-compose.prod.yml up -d kyokki-telegram`.
5. Share a receipt to the bot. It answers "Received", then edits that message with the summary
   after about a minute. `kyokki-worker` reads receipts one at a time; the rest wait in the
   queue and the reply says how many are ahead.

Behaviour worth knowing:
- Sending the same file again (on Telegram or through the upload API) is rejected as already
  received, so a receipt is never imported twice. The API answers 409 with the existing id.
- Photos sent the normal way are compressed by Telegram; send them **as a file** for better OCR.
  Files over 20 MB cannot be downloaded by bots.
- Receipts are queued in the database, so a bot restart loses nothing; they are still read.
  Only the "Received" messages sent before the restart are not edited with the result.
- Without a token the service logs "Telegram bot disabled" and idles.

**Privacy:** receipts pass through Telegram's servers, and a receipt shows what you bought, where
and when, and often the last digits of the payment card. Only allowlisted chats are served;
other chats get no reply except their chat id on `/start`, and nothing they send is logged.
Keep the token secret: anyone with it can read what is sent to the bot. If it leaks, use
`/revoke` in @BotFather and update `stack.env`.

## Operations

Every `docker compose` command for this stack needs `--env-file stack.env`. The compose file
declares `POSTGRES_PASSWORD` with the required form `${POSTGRES_PASSWORD:?}`, which compose
evaluates even for `logs` and `down`, so without it the command either aborts or silently
picks up the repo-root `.env` instead.

```bash
docker compose --env-file stack.env -f docker-compose.prod.yml logs -f kyokki-api      # backend logs
docker compose --env-file stack.env -f docker-compose.prod.yml logs -f frontend        # Next.js logs
docker compose --env-file stack.env -f docker-compose.prod.yml logs -f kyokki-worker   # receipt reading logs
docker compose --env-file stack.env -f docker-compose.prod.yml logs -f kyokki-telegram # receipt bot logs
docker compose --env-file stack.env -f docker-compose.prod.yml logs kyokki-migrate      # schema + seed job
docker compose --env-file stack.env -f docker-compose.prod.yml exec postgres \
  pg_dump -U kyokki_user kyokki > backup-$(date +%F).sql          # database backup
docker compose --env-file stack.env -f docker-compose.prod.yml down                    # stop (data volumes stay)
```

Receipt files and logs live in the named volumes `kyokki_data` and `kyokki_logs` (the database
in `postgres_data`), so they survive redeploys and there is no host path to keep in sync. Copy a
receipt out with `docker compose --env-file stack.env -f docker-compose.prod.yml cp kyokki-api:/app/data/receipts/<id>.pdf .`

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
  outside Docker. Always use `docker compose --env-file stack.env -f docker-compose.prod.yml run --rm kyokki-api ...`.
- **Migrations and models disagree:** CI runs `alembic check`; if you edit a model, add a
  revision with `alembic revision --autogenerate -m "..."` inside the container. New model
  modules must be imported in `app/models/__init__.py`, which `app/db/base.py` re-exports for
  Alembic; otherwise autogenerate cannot see them.
