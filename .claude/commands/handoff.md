# Handoff

Write a bounded delta for the next fresh session. Do not restate the project.

1. Inspect the current SHA of the integration branch, recent merges, open PRs, and the
   `## Current frontier` section of `docs/backlog.md`.

2. Write `HANDOFF.md` from `.claude/templates/HANDOFF-template.md` (gitignore it — a handoff is
   session state, not project canon):

```markdown
# Handoff
Generated-UTC: YYYY-MM-DDTHH:MM:SSZ
Base-SHA: <full 40-character SHA>

## Round delta
## Active PRs and conflicts
## Non-obvious decisions or blockers
## Next action
```

**At most 50 lines and 500 words.** Include only:

- what changed this round;
- conflicts that are *not* obvious from PR metadata;
- decisions and blockers that are expensive to rediscover;
- one exact next action, with the authoritative path or link.

**Exclude:** architecture summaries, full PR narratives, test logs, infrastructure addresses,
durable safety rules (those belong in `CLAUDE.md`), and the frontier section itself — the next
session reads that from the backlog.

3. Check it against the limits: line count, word count, both header fields present, the SHA full
   and real. If `docs/conventions.md` declares a handoff validator under "Round tooling", run it
   and fix every error.

4. State that the handoff is advisory and that canonical architecture, backlog, and source outrank
   it. Then recommend clearing context.
