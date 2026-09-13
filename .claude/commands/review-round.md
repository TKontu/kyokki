# Review a round

Review every PR in the current round, fix small issues, route larger ones back. Do not merge.

1. Follow `CLAUDE.md`. Load the round from `.rounds/<round-id>/round.md` (or from session context).
   Resolve each assignment's PR by branch: `gh pr list --head <branch>`.

2. **Per PR, start from a verdict.** If the project uses `/pr-verdict`, ensure a verdict comment
   exists (marker `<!-- pr-verdict -->`); run `/pr-verdict <n>` for it if missing. Read the verdict,
   then spot-check at least one finding and one "held" claim against the diff yourself — a verdict
   you have not sampled is hearsay.

   If the project does not use the verdict panel, review the diff directly against the assignment's
   spec, using `/review` as the checklist.

3. **Confirm the gates.** CI green, or — for a tier the project's CI skips — run the correct local
   gate: `docs/conventions.md` names those under "Gates that do not run in CI", and the commands
   themselves come from the **Project Commands** table in `CLAUDE.md`. Do not accept "tests pass"
   without seeing which tests actually ran.

4. **Check scope.** Did the PR change only the paths its spec listed as owned? A file outside the
   owned set is a finding even if the change is good, because a sibling may own it this round.

5. **Small issues** — lint, a missing test, a doc line, a clear local bug: fix them directly on the
   PR branch and note exactly what you changed. A PR you pushed fixes to cannot be self-merged;
   flag it for operator confirmation at merge time.

6. **Larger issues** — scope, design, a real defect needing the author's context: do NOT fix in
   place. Print a fenced fix-prompt for that specific executor to apply and update its PR.

7. **Record deviations where they belong** — the backlog item's outcome, a deviation log, or a new
   backlog row. Not just in prose in your report. Never edit the target to make a PR fit.

8. Report per-PR status (`ready` / `awaiting-fix`) and anything needing an operator decision.
   Update the status column in `round.md`. Merging is `/merge-round`.
