# Handoff
Generated-UTC: 2026-09-27T12:00:00Z
Base-SHA: c051950bcbf67033ce723763ef85ea19af07b2d0

## Round delta
- Round 2026-09-27-2 is merged and reconciled, but **not yet deployed**:
  - #125 line accounting, with its follow-up #127;
  - #124 review screen;
  - docs #123 and #126.
- #125 was merged before its review panel. The post-merge verdict found 26 issues, none needing a
  revert, all listed under "Q27 follow-ups" in `docs/TODO.md`.
- Round 2026-09-27-3 is planned and dispatched from `c051950`:
  - C1 Q27 hardening;
  - C2 exact-emoji trial;
  - C3 Q29-Q36 fridge look and shell.
  Specs are in `.rounds/2026-09-27-3/`.

## Active PRs and conflicts
- This reconcile docs PR. The C1-C3 PRs follow.
- C1 and C2 share `c2.muse-glimmer`: C2 uses it early, C1 only for its final re-measure.

## Non-obvious decisions or blockers
- **Operator rulings:**
  - Receipts from any country and language must work, with no hardcoded formats in the core.
    Country parsers are only optional profiles.
  - Multi-line items must always work.
  - LLM-drawn SVG icons are rejected. Exact Apple emoji only, never the closest match; the gaps get
    generated images via ComfyUI behind llama-swap, and the operator will share how to call it.
- **Deploy prerequisites:** set `RECEIPT_STALE_MINUTES=25` (and `LLM_TIMEOUT=420` if the stack sets
  it explicitly). C1 makes this automatic.
- **Hardware:** 2×3090 on the gateway (muse-glimmer plus one co-hosted model) and 3× RTX A2000 12 GB.
  ComfyUI is being deployed behind llama-swap.
- **Environment carried over:**
  - Merges are the operator's.
  - Verdict panels must not draft lens reports themselves; at most 6 agents at once.
  - Executors cannot message "orchestrator"; they report at the end.
  - Never symlink the shared `frontend/node_modules`.
  - The shared venv lacks `defusedxml` (use `pip --target` in scratch).
  - Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
Wait for C1-C3, then run `/review-round`, with verdict panels before any merge this time.
