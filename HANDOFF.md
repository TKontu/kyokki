# Handoff
Generated-UTC: 2026-10-03T11:02:35Z
Base-SHA: 6506cca6c543d439f78fcaa43df0d2202225cf8d

## Round delta
- **Merged on 2026-10-03 (not deployed):**
  - round 2026-10-02-3 (#157-#162) and its reconcile #163;
  - round 2026-10-03-1: #164 e-mail receipts, #165 run-out forecast, #166 H47 Telegram, #167
    min-stock follow-ups, #168 Finnish UI.
- `main` CI and the image builds are green at 6506cca.
- Outcomes are in `docs/TODO.md` after the round 2026-10-02-3 block. The log is
  `.rounds/2026-10-03-1`.

## Active PRs and conflicts
- None open apart from this reconcile. Alembic head: `61f6f69cc22f` (unchanged in round 2026-10-03-1).

## Non-obvious decisions or blockers
- **Display names are not resolution keys.** They live in `product_display_name`, never in
  `product_name`. Whether a cook-set Finnish name should also become a synonym is undecided.
- **Icons:** the template's composition and negative-prompt tuning were measured as harmful and
  reverted. Do not reintroduce them without a new four-way measurement.
- **CI runs only for PRs into `main`.** A stacked PR needs a retarget plus a push before real CI runs.
- **The agent sandbox refuses `ssh`.** The operator opens the ComfyUI tunnel on devbox
  (`ssh -f -N -L 19292:127.0.0.1:9292 sandbox-host`) and closes it with
  `pkill -f "19292:127.0.0.1:9292"`.
- **The agent is denied `gh pr merge` and force-push.** Lanes merge `main` and never rebase.
- **The Sonnet session limit has stopped agents four times.** Executors push early; resume them
  with SendMessage.
- **Operator, in production:**
  - deploy (`kyokki-migrate` applies the two new revisions, c715f1ea4510 and 61f6f69cc22f,
    automatically);
  - icons on: a Caddy allow rule for the server on `/upstream/a4.comfyui/`, then
    `COMFYUI_BASE_URL` in Portainer, then `backfill_icons --dry-run` and the real run;
  - `scripts.backfill_display_names --dry-run`, then the real run;
  - optional: `RECEIPT_WATCH_DIR` and the worker mount (`docs/DEPLOY.md` "Watched folder");
  - optional: e-mail receipts, a dedicated mailbox plus `RECEIPT_MAIL_*` including
    `RECEIPT_MAIL_ALLOWED_SENDERS` (`docs/DEPLOY.md` "E-mail receipts");
  - the Finnish wording pass (list in `docs/TODO.md`, round 2026-10-03-1);
  - remove the aliases `KARTANON KALKKUNALEIKE → Ham` and `VALIO VOI NORMAALISUOLAI → Spread`;
    rename "Dip";
  - `scripts.rekey_store_chains` (dry run, then `--apply lidi-suomi-ky`);
  - `LLM_MAX_TOKENS`; the AG7 Hermes run.
- **Held on operator decisions:** HTTPS on the LAN (frontier 4), which unblocks the Android share
  target and PWA camera scanning; meal sections (frontier 14); AG0 recipes.
- **Round 6 candidates:**
  - language phase 3 (the products, receipt and scan screens);
  - the crud → service inversion;
  - H41 (scanner quarantine, DEC-7), H42 (concurrency tests), H44 (line endings);
  - a Tomato puree icon brief (needs a tunnel session).
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
Merge this reconcile. Deploy is due: several rounds of features are merged but not deployed. Then plan round 6.
