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
  vision-capable model such as `muse-glimmer`), **which needs an API key since 2026-09-30 (see
  the note under "Updating")**. Name the copy pinned to the GPU Kyokki may use
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
> left `processing` for longer than the stale window (`RECEIPT_STALE_MINUTES`; see the Q27 note
> below for its default), for example after the
> worker was restarted mid-read, is shown as `failed` and can be queued again the same way.

> **Receipt line accounting (Q27, 2026-09): check `LLM_TIMEOUT` and `RECEIPT_STALE_MINUTES`.**
> A receipt read now accounts for every priced line and may make one targeted re-read, so a
> long receipt needs more model time. The compose file defaults `LLM_TIMEOUT` to 420 s, but a
> Portainer stack created from an older `stack.env.example` sets `LLM_TIMEOUT=180` explicitly,
> and an explicit value wins over the default: long receipts then still time out. In the
> stack's environment:
>
> - set `LLM_TIMEOUT=420`;
> - clear `RECEIPT_STALE_MINUTES` (leave it empty) or delete it. Empty, the stale window
>   follows the per-receipt budget: OCR (`MINERU_TIMEOUT`) plus the larger of
>   `3 x LLM_TIMEOUT` and `2 x LLM_TIMEOUT + LLM_ESTIMATE_TIMEOUT`, rounded up to minutes,
>   plus 5 (28 minutes with the defaults). A first read and a re-read may each take
>   `LLM_TIMEOUT` and the product selection `LLM_ESTIMATE_TIMEOUT`; the old window of 10
>   minutes failed a slow but healthy receipt. A value below the budget is raised to it, and
>   a receipt that was failed as stale or claimed again is no longer overwritten when its
>   first read finishes late;
> - optionally set `LLM_ESTIMATE_TIMEOUT` (default 180 s), which now limits the catalog
>   estimate and product selection calls instead of `LLM_TIMEOUT`, so "Re-estimate all" does
>   not wait 7 minutes a batch.
>
> Then **Pull and redeploy**. No migration is involved.

> **Gateway API key (GW-1, 2026-09-30): the llama-swap gateway now requires one.** Every
> `/v1/*` request needs `Authorization: Bearer <token>`; without it the gateway answers 401.
> The compose file now declares `LLM_API_KEY` the same required way as `POSTGRES_PASSWORD`
> (`${LLM_API_KEY:?}`), so with it unset every `docker compose -f docker-compose.prod.yml …`
> command - including `logs` and `down` - refuses to run, and the stack will not start at
> all, not just answer 401 once it is up. In the Portainer stack:
>
> - set `LLM_API_KEY` to the llama-swap key, then **Pull and redeploy**;
> - verify from the host (or a container with network access) with:
>   ```bash
>   curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $LLM_API_KEY" \
>     http://192.168.0.94:9292/v1/models
>   ```
>   which must print `200`;
> - health probes and healthchecks must keep hitting `/health`, not `/v1/*` - `/health` needs
>   no key;
> - cold starts take 2 to 5 minutes, longer for a 27B model, so keep `LLM_TIMEOUT` and
>   `LLM_ESTIMATE_TIMEOUT` at 300 s or more, preferably 600 s (see the Q27 note above for
>   how they are used).
>
> No migration is involved.

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

## Watched folder

A third way receipts arrive, alongside the iPad upload and the Telegram bot: drop a PDF or
photo into a folder on the server and `kyokki-worker` reads it like an upload, within a poll
interval. Point a phone or computer sync app at it - Syncthing, a network share, e-receipts
saved from mail - and nothing needs to be manually uploaded.

**Off by default** (`RECEIPT_WATCH_DIR` empty). To turn it on:

1. The compose file already mounts a volume at `/app/receipt-watch` on `kyokki-worker`, named
   `kyokki_watch` by default. To use a real folder on the host instead (so Syncthing or a share
   can write to it directly), set `RECEIPT_WATCH_HOST_DIR` in `stack.env` to that host path,
   e.g. `RECEIPT_WATCH_HOST_DIR=/srv/kyokki/receipt-watch` (create it first; it is bind-mounted
   as-is).
2. Set `RECEIPT_WATCH_DIR=/app/receipt-watch` in `stack.env` - this is the container-side path
   from step 1, and the setting that actually turns scanning on; the mount alone does nothing.
3. Restart the worker: `docker compose --env-file stack.env -f docker-compose.prod.yml up -d
   kyokki-worker`.
4. Point Syncthing (a receive-only folder on the server, synced from the phone's camera roll or
   a "receipts" folder) or your network share client at `RECEIPT_WATCH_HOST_DIR`.

Two more settings, both optional:
- `RECEIPT_WATCH_POLL_SECONDS` (default 10) - how often the folder is scanned.
- `RECEIPT_WATCH_SETTLE_SECONDS` (default 5) - a file must sit unchanged in size and mtime for
  this long before it is taken, so a sync still writing it is never read half-finished.

Behaviour worth knowing:
- The scan is not recursive, and ignores dotfiles, `.syncthing.*` temp files, and files ending
  in `.part`, `.tmp` or `~`.
- A taken file is moved (never deleted) into `processed/` inside the watched folder; the same
  bytes dropped again go to `duplicates/` (the 409 duplicate check, same as every other
  channel); the wrong file type or a file over `MAX_RECEIPT_UPLOAD_BYTES` goes to `rejected/`
  with a `<name>.reason.txt` next to it.
- Logging is INFO-only and never includes file contents.
- The watcher assumes a single `kyokki-worker` replica. Archiving is race-safe against a
  second worker claiming the same name at the same moment (neither file is overwritten),
  but only one replica should run the scan at a time, or the same dropped file could be
  read twice.

## E-mail receipts

A fourth way receipts arrive, alongside the iPad upload, the Telegram bot and the watched
folder: Finnish chains (K-Ruoka, S-kanava, Lidl Plus) can send e-receipts by mail, usually as a
PDF attachment. Point a dedicated mailbox at `kyokki-worker` and it reads each allowed mail's
attachment like an upload, within a poll interval, then moves the mail so it is never read
twice.

**Off by default** (`RECEIPT_MAIL_HOST` empty). To turn it on:

1. Create a **dedicated mailbox** for this - do not point it at a personal inbox. Any IMAP
   provider works; an app password (not the account password) is usually required once
   two-factor or "less secure apps" is involved - Gmail and Outlook both call this "app
   password" in their security settings.
2. In `stack.env`, set:
   - `RECEIPT_MAIL_HOST`, `RECEIPT_MAIL_PORT` (default 993), `RECEIPT_MAIL_USER`,
     `RECEIPT_MAIL_PASSWORD` (the app password).
   - `RECEIPT_MAIL_ALLOWED_SENDERS` - **required**, a comma list of exact addresses or
     `@domain`s. Anyone who knows the mailbox address could otherwise mail in a fake receipt;
     with `RECEIPT_MAIL_HOST` set and this empty, the worker logs one ERROR and never scans.
     List the cook's own address (for manually forwarded mail) and the chains' sending domains
     (for mail rules set up per step 4).
   - Optionally `RECEIPT_MAIL_FOLDER` (default `INBOX`), `RECEIPT_MAIL_PROCESSED_FOLDER`
     (default `Kyokki/Processed`, created automatically), `RECEIPT_MAIL_POLL_SECONDS`
     (default 300).
3. Restart the worker: `docker compose --env-file stack.env -f docker-compose.prod.yml up -d
   kyokki-worker`.
4. Either forward each e-receipt mail by hand (from an allowed address), or set up a mail rule
   / filter in the cook's own mailbox that auto-forwards mail from each chain's e-receipt
   sender to the dedicated mailbox - most mail providers support a rule like "from
   contains @k-ruoka... -> forward to receipts@...".

Behaviour worth knowing:
- Each `application/pdf`, `image/jpeg` or `image/png` attachment becomes one queued receipt,
  including one inside a forwarded (`message/rfc822`) mail - so forwarding the chain's own
  e-receipt mail works, not just a chain sending straight to the mailbox. A PDF always
  counts; an image counts only if it has a filename and no `Content-ID` - a `Content-ID`
  means the mail's own HTML references it (an inline logo, a tracking pixel), not something
  attached for its own sake. An iPhone-forwarded photo still counts.
- A mail with no usable attachment (including an HTML-only e-receipt, which is out of scope)
  or from a sender not in `RECEIPT_MAIL_ALLOWED_SENDERS` is flagged read and left in the
  mailbox, unmoved - nothing else is deleted or changed.
- The same bytes sent again are skipped as already received (the same duplicate check as
  every other channel); the mail still moves to `RECEIPT_MAIL_PROCESSED_FOLDER`.
- Logging is INFO-only, and never includes the subject, body or password - only the sender's
  domain and a reason for anything not queued.
- A mailbox the worker cannot reach is retried on a later poll with a growing backoff, instead
  of failing the worker.

## Generated product icons

**Off until the server can reach ComfyUI.** A food product with no exact Apple emoji (the
"gap", `docs/spikes/Q18_exact_emoji.md`) gets a small generated icon through ComfyUI
(`services/comfyui.py`, `services/icon_workflow.py`, `services/product_icons.py`). The GPU
host's ComfyUI is loopback-only today, so `COMFYUI_BASE_URL` is empty by default and nothing is
queued or shown as an error - tiles fall back to the emoji or the category icon, and the
product sheet says generation is not configured.

Once a route to the GPU host exists, set `COMFYUI_BASE_URL` (and `LLM_API_KEY`, sent on every
ComfyUI request too) in `stack.env` and restart `kyokki-api`. Then queue the existing catalog's
gap products:

```bash
docker compose --env-file stack.env -f docker-compose.prod.yml run --rm kyokki-api \
  python -m scripts.backfill_icons --dry-run
docker compose --env-file stack.env -f docker-compose.prod.yml run --rm kyokki-api \
  python -m scripts.backfill_icons
```

## Agent access tokens

Port 17300 answers anyone on the LAN until `KYOKKI_API_TOKENS` is set. Once it holds at least
one entry, every `/api` request (reads included) needs `Authorization: Bearer <secret>`; the
WebSocket `/api/ws` may pass `?token=<secret>` instead. `/api/health` and `/api/health/live`
stay open for the healthchecks. A `read` token may only `GET`/`HEAD`/`OPTIONS`; a `write`
token may do everything. A missing or unknown token is a 401, a read token on a write a 403.

The iPad never holds a token: the frontend's Next server adds its own (`KYOKKI_PROXY_TOKEN`)
to every `/api` request it proxies. So once tokens are on, the iPad needs an entry too.
That makes port 17301 an open door with the iPad's scope: anyone on the LAN who reaches the
frontend reads and writes as `ipad`. Tokens guard 17300; keep 17301 to the devices you trust.

1. Generate one entry per client. Each command prints a `secret:` (give it to the client, it is
   shown once) and an `entry:` (the name, scope and SHA-256 of the secret, for the config):

   ```bash
   docker compose --env-file stack.env -f docker-compose.prod.yml run --rm --no-deps \
     kyokki-api python -m app.core.api_tokens new ipad write
   docker compose --env-file stack.env -f docker-compose.prod.yml run --rm --no-deps \
     kyokki-api python -m app.core.api_tokens new hermes write
   ```

2. In the stack environment (Portainer, or `stack.env`), set
   `KYOKKI_API_TOKENS=<ipad entry>,<hermes entry>` and `KYOKKI_PROXY_TOKEN=<ipad secret>`.
   Only hashes go in `KYOKKI_API_TOKENS`; a malformed entry stops the API at startup with an
   error that names the entry.
3. Redeploy (Portainer: *Update the stack*; or `up -d`), which restarts `kyokki-api` and
   `frontend` with the new environment. The frontend image needs no rebuild.
4. Verify:

   ```bash
   curl -H "Authorization: Bearer <hermes secret>" http://<host>:17300/api/whoami
   # {"name":"hermes","scopes":["read","write"],"auth_enabled":true}
   curl -i http://<host>:17300/api/inventory                  # 401 without a token
   curl http://<host>:17301/api/whoami                          # via the iPad proxy: "ipad"
   ```

To revoke a client, remove its entry and redeploy. Rejections are logged by `kyokki-api` as
`api_auth_rejected` with the token name (when known) and the path, never the secret.

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
