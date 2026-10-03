# Handoff
Generated-UTC: 2026-10-03T18:40:32Z
Base-SHA: a3b163612b1ed664f84d2a6c820c1742a665f5e8

## Round delta
- **Merged on 2026-10-03:**
  - #170 icon subjects;
  - round 2026-10-03-2: #171 icon library;
  - round 2026-10-03-3: #172 run-out list, #173 Finnish names on rename, #174 Finnish receipt
    screens, #175 icon curation.
- `main` CI and images are green at a3b1636.
- **Deployed 2026-10-03:** rounds up to 2026-10-03-1. The display-name and icon backfills ran in
  production (72 names, 50 icons).
- **The operator was redeploying a3b1636** when the workspace was halted.
- Outcomes are in `docs/TODO.md`. The logs are `.rounds/2026-10-03-{1,2,3}`.

## Active PRs and conflicts
- None open apart from this reconcile. Alembic head: `c9a51b6756c1` (icon_canonical_at).

## Non-obvious decisions or blockers
- **Icons:**
  - curation is in-app on the develop build (`ICON_CURATION_ENABLED=true`): mark → **Download
    bundle** → `apply_icon_bundle.py` → PR;
  - never hand-fix or bulk-export the current generated icons (operator ruling).
- **Production checks after a deploy:**
  - read-only GETs through `http://192.168.0.136:17300` (the Next proxy injects the token);
  - `kyokki-migrate` runs Alembic automatically;
  - scripts run from the API container's bash as `python -m scripts.<name>` (WORKDIR `/app`).
- **ComfyUI from production:** `COMFYUI_BASE_URL=http://192.168.0.94:9292/upstream/a4.comfyui`
  plus `LLM_API_KEY`. The first call after idle cold-starts for several minutes.
- **CI runs only for PRs into `main`.** The agent is denied `gh pr merge` and force-push; the
  operator merges.
- **The Sonnet session limit** can stop agents; resume them with SendMessage.
- **Operator, open:**
  - verify the redeploy (`kyokki-migrate` Exited (0)) and set `ICON_CURATION_ENABLED=true`;
  - optionally `backfill_display_names --refresh-model` (dry run first);
  - the Finnish wording pass (list in `docs/TODO.md`);
  - remove the aliases `KARTANON KALKKUNALEIKE → Ham` and `VALIO VOI NORMAALISUOLAI → Spread`;
    rename "Dip"; `scripts.rekey_store_chains`;
  - `LLM_MAX_TOKENS`; the AG7 Hermes run.
- **Held on operator decisions:** HTTPS on the LAN (the share target and camera scanning), meal
  sections, AG0 recipes.
- **Next round candidates:**
  - Finnish phase 4 (the products screen and ProductEditSheet);
  - the crud → service inversion;
  - H41, H42 and H44;
  - findings from the operator's iPad use.
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
The operator merges this reconcile, verifies the redeploy and uses the iPad. Then plan the next
round from their findings.
