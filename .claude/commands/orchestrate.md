# Orchestrate

Run the full loop: plan from canonical sources, dispatch bounded executors, review, merge,
reconcile, hand off.

1. Follow `CLAUDE.md`, `docs/conventions.md` if present, and
   `.claude/templates/CLAUDE-orchestrator.md`.

2. The loop, one step at a time — each has its own command, and each stops for the operator:

   ```
   /takeoff       orient; bootstrap anything missing
   /status        (optional) tally and feasibility check
   /plan-round n  select parallel-safe items, write specs, emit prompts
                  → operator pastes each prompt into a fresh executor
   /review-round  review every PR; fix small things, route large ones back
   /merge-round   merge the ready PRs, one at a time
   /reconcile     record results, re-point the frontier, write HANDOFF.md
   ```

3. Between steps, report state and stop. The operator dispatches executors, rules on decisions, and
   confirms merges — not you.

4. Never edit the target to make a returned PR fit. A divergence gets recorded (backlog outcome,
   deviation log, or a decision row), and a decision that changes the plan is the operator's.

The reconcile step is the one easiest to skip and the most expensive to have skipped — a round that
is merged but not reconciled leaves the next session pointed at stale work.
