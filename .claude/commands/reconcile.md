# Reconcile the round

Close the round: record results, re-point the frontier, write the handoff. Run after
`/merge-round`. This is the step easiest to skip and the most expensive to have skipped.

1. Follow `CLAUDE.md`. Refresh the integration branch. Then, for each result merged this round:

2. **Record the outcome** where it belongs — the backlog item's outcome field, and the project's
   report or measurement location if it has one. **A negative result is RECORDED, not hidden**, and
   not restated as a partial success.

3. **Ask: do the results change a premise the plan rests on?** Route it — never silently edit the
   target:

   | Situation | Routing |
   | --- | --- |
   | No change | Update the item's status and outcome |
   | Premise shifted, target intact | Add backlog items for the new bottleneck |
   | Roadblock — this line of attack is exhausted | Record the finding; surface the decision to the operator |
   | The result implies the target is wrong | File a non-executable decision row; operator-gated |

4. **Governance routing:** a negative measurement goes to the evidence record; an intentional
   divergence from spec goes to an append-only deviation log; a proposed target change becomes a
   decision row; new work a result creates becomes new backlog items on the right track.

5. **Re-point `## Current frontier`** in `docs/backlog.md` so a fresh `/takeoff` lands on the right
   work. Keep item statuses current.

6. **Close the round log.** Append to `round.md`, ending with the round's honest numbers:

   - **Behaviour delta** — which production behaviour actually changed, or `none — inventory`.
   - **Rework fraction** — PRs or commits correcting prior rounds ÷ total.
   - **Review calibration**, if the project runs verdicts: `N PRs, M findings, K overturned,
     escapes: E`.

   These exist to catch a team that is busy without moving. Report them as measured, including when
   the answer is `none`.

7. **Write `HANDOFF.md`** from `.claude/templates/HANDOFF-template.md` — ≤50 lines and ≤500 words,
   with `Generated-UTC:` and the full `Base-SHA:`. Include only this round's delta, non-obvious
   conflicts, expensive-to-rediscover decisions and blockers, and one exact next action. Exclude
   architecture summaries, full PR narratives, test logs, and the frontier section itself.

8. **List everything that needs an operator decision.** Then recommend clearing context — the
   handoff is advisory, and canonical architecture, backlog, and source outrank it.
