# Handoff
Generated-UTC: 2026-09-26T15:00:00Z
Base-SHA: e00bb67cba91c95dbae02751b43e3db823b5b19c

## Round delta
- Round 2026-09-26-6 is merged (#100-#106). #103 (CLI) and #106 (icon spike) were merged before
  their review fixes; those landed as #107 and #108. #110 added the Sonnet agent types
  (`quick-fixer`, `ci-watcher`) and the routing table in `CLAUDE.md`.
- Round 2026-09-26-3 is **planned, not dispatched**. Specs and prompts are in
  `.rounds/2026-09-26-3/` (local, gitignored); the lanes cut from `f13e1e5`:
  - A1: Q17-B, the Cielo fridge drawn for the portrait iPad;
  - A2: the `kyokki shopping` commands;
  - A3: the agent API follow-ups.
  #110 touched none of their files.

## Active PRs and conflicts
- #109 (this docs PR) records the Cielo/portrait rulings and the round. Merge it before
  dispatch or alongside; the lanes do not touch `docs/`.

## Non-obvious decisions or blockers
- **The iPad is an 8th gen, always portrait, 810×1080 CSS px.** This supersedes every
  "landscape" line in `docs/TODO.md`. The manifest orientation is cosmetic, because iOS ignores
  it for Home Screen apps.
- A1's look is approved from screenshots in its PR (hosted on the orphan branch
  `assets/q17-cielo-portrait`). `assets/q17-fridge-mocks` can be deleted.
- **Awaiting operator rulings:**
  - the Q18 icon route, and the spike doc's multi-field icon design versus the spec's single
    column;
  - #105's apply marking every answered product as `model`.
- **Environment:**
  - Review panels hit the 20-concurrent-subagent limit last round, so run at most about three
    verdict panels at once.
  - Never symlink the shared `frontend/node_modules` into a worktree; a lane emptied it once.
  - Three worktrees under `.claude/worktrees/` are locked by another session. Leave them.
- `HANDOFF.md` stays tracked: `CLAUDE.md`'s definition of done updates it, which overrides the
  /handoff template's "gitignore it".

## Next action
Dispatch round 2026-09-26-3: one executor per `.rounds/2026-09-26-3/prompts/A<n>.md` (preamble
`.rounds/2026-09-26-3/executor-preamble.md`), then `/review-round`.
