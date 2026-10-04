# Handoff
Generated-UTC: 2026-10-03T20:51:07Z
Base-SHA: 83a508cde437f551515862488952fd56d7324fc6

## Round delta
- Merged 2026-10-03: #170 icon subjects, #171 icon library, #172 run-out list,
  #173 Finnish names on rename, #174 Finnish receipt screens, #175 icon curation, #176 reconcile.
- Alembic head `c9a51b6756c1`. Outcomes are in `docs/TODO.md` (round blocks 2026-10-03-2 and -3).
- Production runs rounds up to 2026-10-03-1. The operator was redeploying a3b1636 (#172–#175)
  when the workspace halted; this is unverified.

## Active PRs and conflicts
- None open.

## Non-obvious decisions or blockers
- Generated → canonical icons is an in-app feature of the develop build
  (`ICON_CURATION_ENABLED=true`): mark → Settings **Download bundle** →
  `scripts/apply_icon_bundle.py` → PR. Never hand-fix or bulk-export the current icons
  (operator ruling).
- `kyokki-migrate` applies migrations on every deploy; there is no manual Alembic step.
- ComfyUI from production needs `LLM_API_KEY`. The first call after idle cold-starts for minutes,
  so retry with a long timeout before diagnosing.
- Two planner misses this day came from shared components (ProductSearch in QuickAddSheet, the
  text libs). Check a component's importers before splitting ownership.
- Held on operator decisions: HTTPS on the LAN (the share target and camera scanning), meal
  sections, AG0 recipes.

## Next action
Confirm the redeploy with the operator:
- `kyokki-migrate` Exited (0);
- the Settings "Canonical icons" section appears once `ICON_CURATION_ENABLED=true` is set.

Then plan the next round from their iPad findings plus the open items in `docs/TODO.md`
(Finnish phase 4: products screen; wording pass; crud → service inversion).
