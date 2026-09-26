# Merge a round

Merge every ready PR in the current round. Uses the current round; takes no argument.

1. Follow `CLAUDE.md`. Load the round from `.rounds/<round-id>/round.md`; resolve each assignment's
   PR by branch.

2. **Confirm readiness per PR** before touching anything: reviewed (`/review-round` ran), CI green,
   and mergeable without conflict. Where the project uses verdicts, the PR's `pr-verdict` comment
   is part of readiness — read it. Never re-run a review panel here. The CI and mergeability
   check can go to the `ci-watcher` agent type (Sonnet, read-only); the merge decision stays here.

3. **Merge one at a time**, refreshing the integration branch between merges. Sibling PRs own
   disjoint paths — the round enforced that — so serial merges should not conflict. **If one does,
   stop and report.** A conflict means the ownership analysis was wrong, and that is worth knowing;
   do not silently rebase past it.

4. **Skip** any PR still awaiting an executor fix.

5. **Two-party rule.** For a PR this session pushed fixes to, ask the operator to confirm that
   merge rather than self-merging. You are not an independent reviewer of your own changes.

6. After the last merge, refresh the integration branch, update `round.md` statuses, and report the
   merged set plus anything skipped and why.

Reconciliation is `/reconcile` — merging is not the end of the round.
