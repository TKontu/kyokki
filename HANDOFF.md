# Handoff
Generated-UTC: 2026-10-04T19:05:20Z
Base-SHA: 9842aa080a5041a37d9b4019a8b3074025dddb0b

## Round delta
- Round 2026-10-04-1 merged and deployed 2026-10-04 (`9842aa0`): #179 Finnish products screen and
  product sheet, #178 run-out rate counts only in-stock days (fixed query count), #180 crud imports
  no services (`app/domain/`, `crud/product_name.py`, shims at the old `app.services.*` paths).
- No migration; Alembic head stays `c9a51b6756c1`. Outcomes are in `docs/TODO.md` (round block
  2026-10-04-1). Log: `.rounds/2026-10-04-1/round.md`.
- Production verified read-only after deploy: health ok, `curation_enabled: true`, run-out shape
  unchanged. The operator confirmed Suomi works on the iPad.

## Active PRs and conflicts
- None open apart from this reconcile.

## Non-obvious decisions or blockers
- `lib/i18n/{en,fi}.ts` are single shared dictionaries: two frontend lanes that add UI text in one
  round conflict. Give one lane the files, or split by appended namespace explicitly.
- `app.services.{units,item_status,storage,product_names}` are now re-export shims; new code imports
  `app.domain.*` / `app.crud.product_name`. `tests/test_layering.py` enforces crud and domain rules.
- Port 17300 on the homelab is the API (uvicorn), not the Next app: page routes 404 there.
- After the workspace reboot the container lacked PostgreSQL and Redis; they were reinstalled with
  apt (`postgresql-16`, `redis-server`). Docker is absent. A further reboot may drop them again.
- Icon curation is on in production: mark → Settings **Download bundle** →
  `scripts/apply_icon_bundle.py` → PR. Never hand-fix or bulk-export icons (operator ruling).
- **Operator, open:** the Finnish wording pass (PR #179 "Wording to check" + earlier lists); poor
  model-proposed display names (fix on the sheet, or `backfill_display_names --refresh-model`);
  the two bad aliases and "Dip"; `rekey_store_chains`; `LLM_MAX_TOKENS`; the AG7 Hermes run.
- Held on operator decisions: HTTPS on the LAN, meal sections, AG0 recipes, DEC-6 to DEC-9.

## Next action
The operator merges this reconcile, curates icons and uses the iPad; then `/plan-round` from their
findings plus `docs/TODO.md` (multi-file receipt upload, H42, H44, shim removal).
