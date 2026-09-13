# TODO: {Task name}

**Assignment:** {assignment-id}
**Backlog item:** {ID from docs/backlog.md}
**Branch:** `{branch-name}`
**Base commit:** {full SHA the executor cuts from}
**Priority:** {high | medium | low}

> This spec must stand alone. The executor's workspace has none of the planning artefacts — no
> round directory, no orchestrator notes. Every path, link, and decision it needs is below.

## Context

{Where this fits. What already exists that the executor should build on or leave alone. What was
decided and is not up for reconsideration. Link the exact files and docs to read — by path.}

## Objective

{One sentence. What must be true when this is done.}

## Tasks

### 1. {First task}

**Files:** `{exact/path/to/file}`

**Requirements:**
- {Specific, checkable requirement}
- {Specific, checkable requirement}

### 2. {Second task}

**Files:** `{exact/path/to/other}`

**Requirements:**
- {Specific, checkable requirement}

## File ownership

**You own — may create or modify:**
```
{path/or/glob}
{path/or/glob}
```

**Do NOT touch — owned by sibling assignments this round:**
```
{path/or/glob}
```

Anything not listed as owned is out of scope. If the work requires it, stop and report.

## Exclusive resources

{Name any single-instance resource this assignment holds for the round — a test database, a
device, a port, a live credential — or "none".}

## Constraints

- {Limitation, or decision already made that must not be revisited}
- {Dependency to be aware of}
- Run only the scoped commands below — not the full suite, not a tree-wide lint.

## Test scope

Resolve from the project's **Project Commands** table (`test-one`). Run exactly:

```bash
{scoped test command, e.g. the project's test-one applied to your test file}
```

## Lint scope

Resolve from the **Project Commands** table (`lint`, `format`). Restrict to your files:

```bash
{lint command limited to the files you changed}
{format command limited to the files you changed}
```

## Acceptance

{The observable behaviour that proves this is done — what a reviewer can run or read to confirm
it, not "the code is written".}

- [ ] {Checkable outcome}
- [ ] {Checkable outcome}

## Definition of done

- [ ] All tasks above completed
- [ ] Test written first, watched fail, now passing (scoped)
- [ ] Lint and format clean (scoped)
- [ ] Only owned files changed
- [ ] PR opened with title: `{type}: {description}` and body linking {backlog ID}
- [ ] Completion report includes actual command output
