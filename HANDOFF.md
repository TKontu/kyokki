# Handoff
Generated-UTC: 2026-09-26T16:15:00Z
Base-SHA: 41478a9d2ff4bbc2442d29f876c224bf6ac652a3

## Round delta
- Round 2026-09-26-3 is merged, reconciled and **not deployed**:
  - #113 Q17-B: the Cielo fridge on `/` for the portrait iPad;
  - #111 AG3: the `kyokki shopping` commands;
  - #112 agent API follow-ups;
  - docs #109.
- Each PR had a verdict panel and one fix-up pass. Rulings and follow-ups are in `docs/TODO.md`
  (the Q17 section) and in the rulings list of `docs/agent_TODO.md`.
- The mypy baseline is refreshed; `endpoints/shopping.py` went from 8 to 6.

## Active PRs and conflicts
- The docs PR for this reconcile (`docs/reconcile-2026-09-26-3`) only.

## Non-obvious decisions or blockers
- **Rulings at review (2026-09-26):**
  - The larder sits beside the freezer drawer, not under the fridge.
  - `shopping add --product-id` requires AMOUNT UNIT.
  - The per-minute derived idempotency key is accepted for now: a flip and flip back within one
    minute replays.
- **The CLI matches two backend error strings verbatim** (`Shopping list item <id> not found`,
  `Referenced record does not exist.`). Reword either and the CLI falls back to exit 1. Coding
  the shopping 404s is a follow-up.
- **The main checkout's `frontend/node_modules` is empty** (since 11:37 UTC, before this round).
  Run `(cd frontend && npm ci)` before any frontend work here.
- **Environment carried over:**
  - Merges and force-pushes are the operator's.
  - At most about three verdict panels at a time.
  - Never symlink the shared `node_modules` into a worktree.
  - Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.
  - The six agent worktrees under `.claude/worktrees/` can be removed once no session holds them.
- **Still awaiting operator rulings:**
  - the Q18 icon route and the spike's icon-column design;
  - #105's catalog apply marking agreed answers as `model`.

## Next action
Merge the reconcile docs PR. Deploy per `docs/DEPLOY.md`, look at `/` on the iPad, then rule
on Q18 so the next round (`/plan-round`) can take Q18 and the portrait pass on the other screens.
