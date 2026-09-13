# Takeoff

Orient a fresh session. Bootstrap anything missing. Do not select or start work.

## 1. Read the project's own instructions

`CLAUDE.md` first, then whatever it points at. If the project has a separate agent contract
(`AGENTS.md`, `CONTRIBUTING.md`, `docs/conventions.md`), read that too. Those outrank this command
wherever they disagree.

## 2. Inspect the repository — do not mutate it

```bash
git status --short && git branch --show-current && git log --oneline -5
```

```bash
gh pr list --state open 2>/dev/null || echo "no gh / not a GitHub remote"
```

Report if the workspace is dirty or the local integration branch is behind. Do not pull, stash, or
clean during orientation.

## 3. Bootstrap what is missing

Check for each, and offer to create it from the template — create it only if the user agrees:

| Missing | Create from | Why |
| --- | --- | --- |
| `CLAUDE.md` | `.claude/templates/CLAUDE-default.md` + a stack profile | Every command needs the Project Commands table |
| the `claude:commands` table in `CLAUDE.md` | inferred from the manifest, confirmed by the user | Commands otherwise have to guess the toolchain |
| `docs/backlog.md` | `.claude/templates/backlog-template.md` | The round workflow reads and writes it |
| `docs/conventions.md` | see below | Holds the few settings the commands cannot infer |

`docs/conventions.md` is short and optional. It holds only what cannot be derived:

```markdown
# Conventions
- **Integration branch:** main
- **Branch naming:** feat/<slug>, fix/<slug>, chore/<slug>
- **Exclusive resources:** <single-instance things at most one assignment may hold per round —
  a test database, a device, a live credential, a port. "none" if there are none.>
- **Round tooling:** <optional validation scripts, if the project has any. "none" — the round
  workflow needs no scripts.>
- **Gates that do not run in CI:** <tiers a reviewer must run locally, and the exact command.>
```

If the project is a bare repo with none of this, say so plainly and offer the bootstrap. Do not
pretend to orient against files that do not exist.

## 4. Build the mental model

From `README.md`, read only the durable sections — what it is for, how it works, architecture,
repository layout. **Do not treat README status or roadmap text as current state**; it is almost
always stale. Do not load the full architecture yet.

## 5. Read the current state

`docs/backlog.md`, in full through the `## Current frontier` section. The backlog is canonical for
maturity and priority — not the README, not a handoff.

## 6. Check the handoff, if there is one

If `HANDOFF.md` exists, compare its `Base-SHA` to the integration branch:

- **Equal** → current.
- **Ancestor** → stale; reconcile the intervening commits and say what landed since.
- **Not an ancestor** → invalid; ignore it and rebuild state from git, PRs, and the backlog.

A handoff is advisory. Canonical architecture, backlog, and source outrank it every time.

## 7. Output a Takeoff Brief

- Purpose and the major flows
- Current maturity, from the backlog
- What changed since the handoff
- Open PRs and any conflict map
- The prioritized immediate frontier
- Handoff freshness
- Anything missing that was bootstrapped or offered
- Recommended next reads

## 8. Stop

Do not select a backlog item, load task-specific architecture, or generate an executor prompt.
That is the next step, and it is the user's call.
