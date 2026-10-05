# Handoff
Generated-UTC: 2026-10-04T19:14:19Z
Base-SHA: e84646ebe879b75bf4d58731427b92dcd426e845

## Round delta
- Round 2026-10-04-1 is merged, deployed and reconciled (#178 to #181):
  - Finnish products screen and product sheet (#179);
  - run-out rate counts only in-stock days, with a fixed query count (#178);
  - crud imports no services (#180): code in `app/domain/` and `crud/product_name.py`, shims at the
    old `app.services.*` paths.
- No migration; Alembic head `c9a51b6756c1`. Outcomes are in `docs/TODO.md` (round block 2026-10-04-1).
- Operator: "Suomi works"; some model-proposed Finnish names are poor ("surface level").
- Icon curation is enabled in production.

## Active PRs and conflicts
- None open.

## Non-obvious decisions or blockers
- **HTTPS is NOT a blocker.** Production already serves the app over HTTPS (Let's Encrypt; the
  operator pointed it out 2026-10-04). `docs/TODO.md` still lists "HTTPS on the LAN" as held on
  the operator (frontier 4, the round blocks). Correct that when planning. The Android share target
  (a `share_target` in `frontend/app/manifest.ts`, absent today) and PWA camera
  scanning are therefore plannable forward lanes.
- `lib/i18n/{en,fi}.ts` are single shared dictionaries. Two frontend lanes that add UI text in one
  round conflict unless one owns them or the namespaces are split explicitly.
- After the reboot the container lacked PostgreSQL and Redis; they were reinstalled with apt
  (`postgresql-16`, `redis-server`). Docker is absent. A further reboot may drop them again.
- Still held on the operator: meal sections, AG0 recipes, DEC-6 to DEC-9; the Finnish wording pass.

## Next action
`/plan-round` from `docs/TODO.md`: first correct the stale HTTPS-held lines, then weigh the share
target, camera scanning and multi-file receipt upload as forward lanes.
