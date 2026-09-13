# Status

Read-only backlog status and feasibility assessment. Mutates nothing. Opens no PRs.

1. Follow `CLAUDE.md` and the project's agent contract if it has one. Refresh knowledge of the
   integration branch (`git log --oneline -5`) but do not mutate the workspace.

2. Use `docs/backlog.md` as the status source — never the README, never a handoff. If the project
   keeps its backlog elsewhere, use that and say which. If there is no backlog, say so and stop;
   `/takeoff` bootstraps one.

3. **Tally mechanically, then verify before reporting.** Adapt the parse to the backlog's actual
   table shape — check the header row first rather than trusting this snippet:

   ```bash
   awk -F'|' '/^\| *[A-Z]+-[0-9]+ *\|/ {gsub(/ /,"",$2); gsub(/ /,"",$3); split($2,a,"-"); print a[1]"\t"$3}' docs/backlog.md | sort | uniq -c
   ```

   Spot-check the counts against the file. A parse that silently misses rows produces a confident
   wrong number, which is worse than no number.

## Section 1 — Done / total per track

One row per track the project defines. Give `done / total` plus the `ready` / `active` / `blocked`
breakdown.

Then add the honesty nuance, both directions:

- Which blocked items are blocked **by design** (waiting on a gate that is supposed to come later)
  versus blocked on an unresolved dependency or an open decision.
- `active` items may be substantially complete — count the landed parts from the row text.
- `done` items may carry named debts that were deferred. Say so.

## Section 2 — Current development situation

What the last one or two rounds landed. What the critical path is now. Where the bottleneck sits —
build, measurement, or an operator decision. List the open decision rows.

## Section 3 — Feasibility on current knowledge

Separate the confidence levels honestly rather than averaging them into one verdict:

- **Engineering feasibility** — what is built and proven to run, and what is still unproven.
- **Validation feasibility** — what the project's own measurements say, cited with numbers, and
  what gates the next measurement.
- **Newly sized risks** — anything recent work made bigger or smaller.

Cite measured numbers, never impressions. A negative result is reported as-is.

## Section 4 — Premise check

Has any recent increment changed a premise the plan rests on? Classify each candidate:

- no change;
- premise shifted but the target is intact;
- roadblock — this line of attack is exhausted;
- the result implies the target itself is wrong.

Say whether the backlog already records the routing, or whether an operator decision is missing.

## Stop

Do not edit any file, select work, or open a PR. Surface gaps as recommendations only.
