# Round {round-id}

**Base:** {full 40-character SHA} on `{integration branch}`
**Opened-UTC:** {YYYY-MM-DDTHH:MM:SSZ}
**Status:** planned | dispatched | reviewed | merged | reconciled

> Copy to `.rounds/{round-id}/round.md`. Plain markdown by design — no helper script is required
> to plan, review, or merge a round. If the project has round tooling, it is declared under
> **Round tooling** in `docs/conventions.md`.

## Assignments

| # | Item | Class | Branch | Owned paths | Exclusive resource | Spec | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | FEAT-001 | forward | `feat/...` | `src/x/**` | none | `specs/A1.md` | planned |
| A2 | QUAL-002 | maintenance | `chore/...` | `tests/y/**` | none | `specs/A2.md` | planned |

- **Class** — `forward` (the system can do something new) or `maintenance` (everything else).
- **Owned paths** must be disjoint across rows. Verify against source, not against the backlog's
  claim.
- **Exclusive resource** — at most one row per resource per round.
- **Status** — `planned` → `dispatched` → `pr-open` → `reviewed` → `merged`, or `awaiting-fix`.

**Forward : maintenance = {n}:{m}.**
{If forward lanes are short, name the blocked forward items that would have filled them and what
unblocks each.}

## Preflight

Checked before dispatch:

- [ ] Base SHA is current on the integration branch (no drift since it was recorded)
- [ ] Every item is `ready` or `active` in `docs/backlog.md` as of the base commit
- [ ] Owned path sets are disjoint, verified against source
- [ ] No branch in the table already exists on the remote
- [ ] At most one assignment per exclusive resource
- [ ] Every spec stands alone — no reference to this file or to orchestrator-only paths

## Log

| UTC | Event |
| --- | --- |
| {timestamp} | Round opened at {SHA} |
