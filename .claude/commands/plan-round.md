# Plan a round

Plan AND assign a parallel-safe batch, then emit one ready executor prompt per assignment.
Argument: `<n>`, how many items to parallelize. Do not launch executors and do not merge.

## 1. Base

Follow `CLAUDE.md` and `docs/conventions.md` if it exists. Start from a fast-forwarded integration
branch and **record its full SHA as the single round base**. Every assignment cuts from that one
commit.

## 2. Select up to `<n>` parallel-safe items

From `docs/backlog.md` "Current frontier". An item may join the round only if:

- Its **owned paths are disjoint** from every sibling's — no shared file, no shared module both
  would edit.
- It needs no **exclusive resource** already claimed this round (see `docs/conventions.md`).
- It does **not depend on a sibling's output**. Dependent work goes in the next round.

**Verify every ownership claim against the source before dispatching on it.** A backlog row saying
an item "only touches X" has been wrong in both directions. Open the files.

If fewer than `<n>` items are parallel-safe, plan fewer and say why.

## 3. Classify every lane

- **Forward** — the system can do something it could not before.
- **Maintenance** — everything else. A behaviour-frozen refactor and a measurement-only lane are
  *always* maintenance, whatever item they hang off.

Aim for a majority of forward lanes. Below that the round may still run, but the dispatch table
must name which blocked forward items would have filled those lanes and what unblocks each — a
round that cannot reach the ratio is evidence of a stalled decision, so surface it as one. Never
spend an exclusive resource on a maintenance lane while a high-priority item needs that same
resource.

## 4. Materialize the round

Create `.rounds/<round-id>/` (round id: `YYYY-MM-DD-<n>`; gitignore `.rounds/`):

```
.rounds/<round-id>/
├── round.md          from .claude/templates/round-template.md
├── specs/A1.md …     one per assignment
└── prompts/A1.md …   what the operator pastes into each executor
```

Fill in `round.md`: base SHA, and one row per assignment with item, class, branch, owned paths,
exclusive resource, spec path, status `planned`.

If `docs/conventions.md` declares **Round tooling**, use those scripts to generate and validate
instead of hand-writing. Most projects have none — plain markdown is the supported path, not a
fallback.

## 5. Write each spec

Use `.claude/templates/TODO-agent-template.md`. Write the task-specific body: context with real
paths, objective, in/out of scope, contract specifics, acceptance.

**Each spec must stand alone.** The executor's workspace is cut from the integration branch and has
no `.rounds/` directory — it cannot read `round.md`. So every scope link, the base SHA, the owned
paths, the sibling do-not-touch list, and the scoped test and lint commands go *into the spec
itself*. Never make reading the round manifest a prerequisite for an executor.

Resolve the scoped test and lint commands from the **Project Commands** table in `CLAUDE.md` and
write the concrete commands into the spec — not the key names.

The planner owns new IDs and frontier text; add rows to `docs/backlog.md` for any new item this
round introduces.

## 6. Preflight

Check every item in the round template's preflight list and fix every failure before dispatch:

- Base SHA still current — no drift since you recorded it
- Every item `ready` or `active` in the backlog as of the base commit (a stale checkout cannot
  re-open a closed item)
- Owned path sets disjoint, verified against source
- No branch already exists on the remote
- At most one assignment per exclusive resource
- Every spec self-contained

## 7. Emit the dispatch table — not the prompts

Do **not** read the rendered prompts back into context or print them inline. You just wrote and
checked them; re-emitting only burns context without improving accuracy.

End with the dispatch table from `round.md` — per assignment: id, item, **class**, branch, prompt
path — with the forward:maintenance ratio stated above it. Tell the operator to paste each
`prompts/A<n>.md` into one fresh executor session using `.claude/templates/CLAUDE-executor.md` as
that workspace's `CLAUDE.md`.

Print a prompt's full text inline only if the operator explicitly asks.

## 8. Stop

The round directory is the record `/review-round` and `/merge-round` read.
