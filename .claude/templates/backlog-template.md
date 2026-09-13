# Backlog

> Copy to `docs/backlog.md`. This is the single source of truth for planned, active, and done
> work — not the README, not a handoff, not a PR description. Commands in `.claude/commands/`
> read and update it.

## How to read this

- **ID** — `<TRACK>-<n>`. Tracks are this project's own; define them in the Tracks table below.
- **Status** — one of `ready` (specified, dispatchable), `active` (in flight), `blocked`
  (waiting on something named), `done` (merged and verified).
- Rows are append-only. Change a status in place; never delete history. A cancelled item becomes
  `done` with an outcome saying it was dropped and why.
- A row that needs more than one line of detail links to a section under **Detail**.

## Tracks

| Track | Meaning |
| --- | --- |
| `FEAT` | User-visible capability |
| `INFRA` | Build, deploy, tooling, CI |
| `QUAL` | Tests, refactors, debt, hardening |
| `DEC` | Decisions and proposals — not executable work; needs an operator ruling |

<!-- Rename or replace these to match the project. Keep DEC (or an equivalent) so decisions that
     block work are visible as rows rather than lost in prose. -->

## Current frontier

<!-- What to work on next, and why. `/takeoff` reads this to orient; `/plan-round` picks from it;
     `/reconcile` re-points it after every round. Keep it to a short paragraph plus the ranked
     candidate IDs. -->

{One paragraph: where the work stands and what the bottleneck is.}

**Next up:** {ID}, {ID}, {ID}

## Items

| ID | Status | Title | Owns | Blocked by |
| --- | --- | --- | --- | --- |
| FEAT-001 | ready | {one-line title} | `src/x/**` | — |
| QUAL-001 | blocked | {one-line title} | `tests/y/**` | FEAT-001 |
| DEC-001 | ready | {a decision the operator must make} | — | — |

- **Owns** — the file paths the item is expected to change. `/plan-round` uses this for parallel
  safety, so keep it honest and verify it against source before dispatching on it.
- **Blocked by** — an ID, or a named external condition. Never leave it as a bare "blocked".

## Detail

### FEAT-001 — {title}

**Goal:** {what becomes true}
**Approach:** {the agreed shape, if one is agreed}
**Acceptance:** {how it is judged done}
**Outcome:** {filled in at reconcile — including a negative result, recorded as-is}

## Decisions

| ID | Question | Status | Ruling |
| --- | --- | --- | --- |
| DEC-001 | {what must be decided} | open | — |

Decisions are operator-gated. An agent may file one and lay out the options; it may not rule on
one, and it may not silently pick an option and proceed.
