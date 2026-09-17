# Handoff
Generated-UTC: 2026-09-14T20:30:00Z
Base-SHA: d77c849

## Round delta
- #41 MVP-S4 merged: item edit sheet (correct, mark as gone, delete with history).
- MVP-R3b on `feat/mvp-r3b-heuristic-fallback` (PR open): a store-agnostic line parser reads text
  receipts when the model fails or finds nothing (`extraction_method = "heuristic"`,
  `fallback_reason`). Heuristic receipts can be re-read with `/process`. No migration.

## Active PRs and conflicts
- R3b PR. Wave 3 then has only R4 (real-receipt validation on the homelab), which needs the
  deployed stack and MinerU. Wave 4 (R5-R8 receipt screens) starts when Wave 3 is merged; the
  operator can decide to start Wave 4 before R4 if homelab deployment waits.

## Non-obvious decisions or blockers
- LLM: llama-swap `http://192.168.0.94:9292/v1`, `muse-glimmer` (always loaded, one slot).
  `reasoning_strength` only `xhigh|high|medium|low`; use `low`. Only GPU `GPU-a8c640ca-...`.
  MinerU was still unreachable on 2026-09-14, so images use vision (no heuristic fallback there).
- Heuristic parser: `app/parsers/heuristic.py`; skip list shared with the LLM prefilter in
  `app/parsers/receipt_lines.py`. Test fixtures in `backend/tests/fixtures/receipts/`.
- Products are generic English names; heuristic rows have none (names as printed), so only
  aliases and printed-name matches apply until the model re-reads.
- Receipts: queue `queued -> processing -> completed | failed -> confirmed`; `kyokki-worker` must
  run (locally `python -m app.worker`).
- Stock status rules live in `crud/inventory_item.apply_quantity_status` (consume + corrections).
- Agent track (HTTP API + `kyokki` CLI + SKILL.md, no MCP, agent on the LAN) is planned in
  `docs/agent_TODO.md` and starts after MVP-P3.
- Always run backend pytest through the scratch `rt.sh` (moves the legacy root `.env` aside);
  a direct run prints the legacy `.env` values in the settings error.
- Browser checks: the automation tab is hidden; drive the UI with `javascript_tool`.
- Non-idempotent mutations (consume, delete, confirm, quick add) use `retry: false`.
- Operator items still open: rotate Postgres password + LLM key (and the legacy root `.env`
  keys), purge `stack.env` history, deploy on the homelab and confirm the iPad renders
  inventory, create the Telegram bot.

## Next action
Merge R3b. Then R4 on the homelab (deploy, MinerU, five real receipts), or ask the operator to
start Wave 4 (R5 receipt API module and polling hooks) while R4 waits for the homelab.

## Deployment (2026-09-16)
- `.github/workflows/images.yml` publishes `ghcr.io/tkontu/kyokki-backend` and `-frontend` on
  every push to main (`latest` + `sha-<commit>`). The packages must be public once.
- `docker-compose.prod.yml` builds nothing: it pulls those images and takes configuration from
  environment variables (Portainer stack env; `stack.env.example` is the paste-ready list).
  `docker-compose.build.yml` is the local-build override.
- A one-shot `kyokki-migrate` service runs `alembic upgrade head` + the category seed before the
  API, worker and bot start, so a Portainer redeploy needs no console step. It shows as
  `Exited (0)`.
- Receipt files and logs are named volumes (`kyokki_data`, `kyokki_logs`), not host paths.
- Verified locally with the build override: migrations ran, all services came up, and a receipt
  went through MinerU + `c2.muse-glimmer` in 65 s.
- The repo is public, so GitHub-hosted Actions minutes are free; a self-hosted runner with a
  mounted Docker socket would be a security risk on a public repo (fork PRs run arbitrary code).

## Receipt review (2026-09-16)
- `/receipt/[id]` is the review screen and `ReceiptsBanner` on the home page is the way in.
  That closes the loop the operator asked for: drop a receipt to the bot, review it, stock
  appears, consume it.
- Receipt data lives in `lib/api/receipts.ts` + `hooks/useReceipts.ts`; polling is in the pure
  helpers `detailPollInterval` / `listPollInterval`, so tests never wait on real timers.
- A line with no category starts skipped; picking one includes it. Matched lines go to their
  product and need no category.
- Still open in Wave 4: R6 (iPad upload page) and R8 (receipts list). Attaching an existing
  product per line is also deferred until the catalog is worth searching.

## App shell, scan and receipts list (2026-09-16)
- `AppShell` (`components/layout/`) is mounted in `app/layout.tsx`, so navigation is everywhere:
  Stock, Scan, Receipts. Pages still own their header and their actions. Add a route by adding
  it to `DESTINATIONS`.
- `/scan` uploads from the iPad; `/receipts` is how you get back to a receipt you left. Both the
  Telegram bot and `/scan` land in the same queue.
- `GET /api/receipts` now answers with `ReceiptSummary` (no OCR text, no items) and takes
  `limit`/`offset`. Anything that needs the items must fetch the receipt itself.
- Uploading a file that is already in the system is not an error: the 409 carries `receipt_id`
  and `/scan` opens that receipt. `APIError.details` now carries an object `detail`.
- **MVP-R4 is ready to measure.** Each read logs `ocr_seconds`, `llm_seconds`, `total_seconds`,
  `method` and the counts; `JSONFormatter` publishes extras instead of dropping them. Five real
  receipts through the deployed stack and R4 is done. Local dry run: OCR 0.1 s, model 60.2 s,
  49 items.
- The operator raised six quantity/consumption issues (pieces vs weight, per-product units and
  shelf life, better consume buttons, non-food filtering, opened tracking). They are logged in
  `docs/TODO.md` under the post-MVP frontier as F1-F6; not before MVP-P3.
- Rotate the legacy root `.env` keys: starting a backend process with it in place makes
  pydantic print the forbidden extras *with their values*. Always move it aside first.

## PWA, dark mode and always-on refresh (2026-09-17)
- `Add to Home Screen` now gives a real app: `app/manifest.ts`, `metadata.appleWebApp` and
  `metadata.icons` in `app/layout.tsx`, icons in `public/icons/`. Branding constants live in
  `lib/brand.ts`; regenerate the PNGs with `python frontend/scripts/make_icons.py`.
- `next/og` (`ImageResponse`) cannot prerender on Windows, so the icons are committed PNGs
  rather than generated at build time. Do not "improve" this back into `ImageResponse`.
- `frontend/Dockerfile` copies `public/` now. Standalone output omits it, so anything added
  there 404s in production without that line.
- The stock list polls every 30 s (`INVENTORY_POLL_MS`). Before MVP-P2 nothing but receipts
  polled, even though ARCHITECTURE.md said otherwise.
- **Dark mode follows the device** and can be forced with `.dark`/`.light` on `<html>`, which
  is how to check it in a browser. Watch for two traps this uncovered: Tailwind's `content`
  must include `lib/`, and `getComputedStyle` returns a live object - snapshot it into a plain
  object before toggling the class, or every reading looks identical.
- The app needs **iPadOS/Safari 15+**; the 1st-gen iPad Air (iPadOS 12.5) renders a blank page
  and cannot be fixed from our side. Evidence is in `docs/DEPLOY.md` prerequisites.
- Still open: **MVP-R4** wants five real receipts through the deployed stack, and **MVP-P3** is
  the acceptance week. PR #46 (P1+R6+R8) must merge before this branch.

## Products know their own shape (2026-09-17)
- `product_master.avg_piece_grams` is new (migration `e7a4c9d2b810`); `default_unit` and
  `default_shelf_life_days` already existed but were frozen copies of the category's. All three
  are now set from what the model works out while reading the receipt (`pw` and `sl` in the
  extraction contract).
- **`quantity_for_product` in `generic_products.py` is the seam.** Both receipt confirm and quick
  add pass through it, and it is the only place with the resolved product in hand, so any future
  "store it the way this product is counted" rule belongs there, not in `units.py` (pure
  arithmetic) and not in the Pydantic validators (no session, product not yet resolved).
- A later receipt fills in gaps but never overwrites — `ProductResolver._fill_gaps`. Do not
  "simplify" that into an unconditional assignment or every shop will undo corrections.
- The extra fields cost ~27 % model time (76.5 s vs 60.2 s on the same 49-line receipt) for no
  loss of accuracy. Worth watching if more fields are ever added to the contract.
- Friction items renamed **F1-F6 -> Q1-Q6** to stop colliding with `MVP-F1`/`MVP-F2`. Q2, Q3 and
  Q6 are done; **Q1** (non-food), **Q4** (consume buttons that fit the item) and **Q5** (opened
  tracking) remain, and Q4 should bring the product editor that Q2 deliberately left out.

## Consume options and the opened clock (2026-09-17)
- `consumptionOptions` (`frontend/lib/consumption.ts`) now derives the buttons from the item;
  `ConsumptionOptionKey` is an open string and options carry `primary`, which the sheet renders
  full width. Counts that would finish the item are not offered - `All n` is that button.
- Opening an item shortens its expiry (`_start_opened_clock` in `crud/inventory_item.py`),
  only ever inwards. **The guard is `avg_piece_grams`, not the unit**: milk is stored as `1 pcs`,
  so gating on `pcs` would exempt every carton. Do not "simplify" it back to a unit check.
- The extraction contract now carries `pw`, `sl` and `os`. The instruction to skip them for
  known products lives *inside* the conditional known-products block, so an empty catalog is
  never told to skip anything.
- **Watch out:** `parse_completion` matches the category case-insensitively because the gateway
  does not reliably enforce the strict `json_schema` enum - the model answers `"Dairy"` for
  `dairy`. A case-sensitive compare silently nulls every category and confirm then creates
  nothing. This was a live bug on `main`, not something this branch introduced.
- Extraction cost is noisy: 60.2 s (no estimates), 76.5 s (two), 67.4 s (three) on the same
  receipt. Do not draw conclusions from single runs.
- Remaining friction: **Q1** (non-food) and the **product editor** that Q2 and now Q4 have both
  deferred.
