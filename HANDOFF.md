# Handoff
Generated-UTC: 2026-10-03T08:06:53Z
Base-SHA: 03588d1cfecdf22026c5972b7cd3a89951d480f2

## Round delta
- **Merged on 2026-10-03 (not deployed):** round 2026-10-02-3, complete: #157 stack.env icon keys,
  #158 watched-folder receipts, #159 iPad API contract, #160 icon subjects (9/12), #161 min-stock
  auto-add, #162 display language phase 1. `main` CI and the image builds are green at 03588d1.
- Rounds 2026-10-02-1 and -2, plus #142, were all merged on 2026-10-02.
- Outcomes are in `docs/TODO.md` after the round 2026-10-02-2 block. The log is
  `.rounds/2026-10-02-3`.
- `docs/PRODUCT_RESOLUTION_SPEC.md` now describes Q37b (the rejected proposal, its correction,
  and the confirm guard).

## Active PRs and conflicts
- None open apart from this reconcile. Alembic head: `61f6f69cc22f` (product_display_name).

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
  - deploy, then `alembic upgrade head` (two new revisions since the last deploy:
    c715f1ea4510 and 61f6f69cc22f);
  - icons on: a Caddy allow rule for the server on `/upstream/a4.comfyui/`, then
    `COMFYUI_BASE_URL` in Portainer, then `backfill_icons --dry-run` and the real run;
  - `scripts.backfill_display_names --dry-run`, then the real run;
  - optional: `RECEIPT_WATCH_DIR` and the worker mount (`docs/DEPLOY.md` "Watched folder");
  - remove the aliases `KARTANON KALKKUNALEIKE → Ham` and `VALIO VOI NORMAALISUOLAI → Spread`;
    rename "Dip";
  - `scripts.rekey_store_chains` (dry run, then `--apply lidi-suomi-ky`);
  - `LLM_MAX_TOKENS`; the AG7 Hermes run.
- **Round 5 candidates:**
  - language phase 2 (UI text; display names on Gone and shopping rows);
  - min-stock follow-ups (the crud → service layering in discard; undo and auto items);
  - the shopping page passes its remove key explicitly;
  - a Tomato puree icon brief;
  - H47 Telegram hygiene.
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
Merge this reconcile, then plan round 5.
