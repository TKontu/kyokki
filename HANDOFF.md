# Handoff
Generated-UTC: 2026-10-02T17:22:38Z
Base-SHA: f4874abfc3f5ce3d996933a4452e2eca733dfc37

## Round delta
- **Merged on 2026-10-02 (not deployed):**
  - round 2026-10-02-1, complete: #144 store chain, #147 agent discard-expired, #148 shopping screen,
    #149 undo direction, #150 waste trend;
  - round 2026-10-02-2, partial: #151 H27 parser, #154 Home Assistant REST.
- **Open and ready:**
  - #153 Q37b;
  - #152 shopping live updates and #155 CLI discard with coded shopping errors. Both were retargeted
    from their stacked parents to `main`, and `main` was merged in so CI runs.
- **#142 Q18-G2:** the live ComfyUI check is running through the operator's tunnel.
- Outcomes are in `docs/TODO.md` after the round 2026-10-01-1 block. The logs are `.rounds/2026-10-02-1`
  and `.rounds/2026-10-02-2`.

## Active PRs and conflicts
- None of #142, #152, #153 or #155 share files.
- #142 owns the only new Alembic head (c715f1ea4510, on fbf2c08da52d).

## Non-obvious decisions or blockers
- **Q37b rulings:**
  - the confirm guard applies only to the name the server served;
  - a name the cook typed is explicit;
  - an accepted correction learns an unverified alias.
- **CI runs only for PRs into `main`.** A stacked PR needs a retarget plus a push before real CI runs.
- **The agent sandbox refuses `ssh`** ("Containment Escape"). The operator opens the tunnel:
  `ssh -f -N -L 19292:127.0.0.1:9292 sandbox-host` on devbox. Close it with
  `pkill -f "19292:127.0.0.1:9292"`.
- **The agent is denied `gh pr merge` and force-push.** Lanes merge `main` and never rebase.
- **The Sonnet session limit has stopped agents three times.** Re-run lost lenses; executors push early.
- **Operator, in production:**
  - remove the aliases `KARTANON KALKKUNALEIKE → Ham` and `VALIO VOI NORMAALISUOLAI → Spread`;
  - rename "Dip";
  - run `scripts.rekey_store_chains` (dry run, then `--apply lidi-suomi-ky`);
  - deploy, including `alembic upgrade head` once #142 merges;
  - `LLM_MAX_TOKENS`;
  - the AG7 Hermes run.
- **Round 4 candidates:**
  - the iPad reads `detail.code` and sends an Idempotency-Key on shopping remove;
  - dedupe the undo TS types;
  - update `PRODUCT_RESOLUTION_SPEC.md` for Q37/Q37b;
  - H47 Telegram hygiene.
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
When the CI watcher and the live check report: post the #142 live-check verdict and have the operator
merge #142, #152, #153 and #155. Then reconcile and plan round 4.
