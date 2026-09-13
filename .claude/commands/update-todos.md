# Update the backlog

Bring `docs/backlog.md` into line with what this session actually landed.

## Context

```bash
git log --oneline -10
```

```bash
git diff --name-only $(git merge-base HEAD @{u} 2>/dev/null || echo HEAD~5)
```

## Instructions

1. **Find the backlog.** `docs/backlog.md` is the convention (see
   `.claude/templates/backlog-template.md`). If the project keeps it elsewhere — `TODO.md`,
   `docs/todo*.md`, an issue tracker — use that instead and say which you used.

2. **Identify this session's work** from the log and diff above. Only what actually landed counts;
   work in progress stays `active`, not `done`.

3. **Update the rows that moved.** Set status, and record the outcome where the item has a detail
   section. A negative or inconclusive result is recorded as-is — never quietly dropped, and never
   restated as a success.

4. **Add what the work revealed.** New tasks, follow-ups, and newly discovered blockers become new
   rows with their own IDs. A blocker names what it is blocked on.

5. **Re-point `## Current frontier`** if this session changed what should happen next.

Only touch items related to this session's work. Do not audit or re-flow the whole backlog, and do
not delete rows — a cancelled item becomes `done` with an outcome explaining why it was dropped.
