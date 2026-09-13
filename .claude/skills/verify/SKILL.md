---
name: verify
description: Use before claiming work is complete - run verification commands and confirm output
---

# Verification Before Completion

## The Rule

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

## Before saying "done"

Resolve the commands from the **Project Commands** table in `CLAUDE.md` (between the
`claude:commands` markers) and run them, in this order:

1. **Tests** — `test`, or the scoped `test-one` if your spec limits you to a subset.
   Must show: all pass, zero failures.
2. **Lint** — `lint`. Must show: clean.
3. **Types** — `typecheck`, where the project has one. Must show: clean.
4. **Build** — `build`, where the change could break it.

A key that is absent or `n/a` is **skipped and reported as skipped**. Never substitute a tool the
project does not use, and never quietly drop a step.

## Read the output

Running a command is half of it. Actually read what came back:

- A suite that reports `0 passed` passed nothing — check the selection.
- Skipped, xfailed, or filtered-out tests are not passing tests. Say how many were skipped.
- A linter that exits 0 because it matched no files has not linted anything.
- An exit code of 0 from a command that printed errors still means something is wrong.

## Evidence format

Report the actual commands and their actual output. Copy it; do not paraphrase it.

```
Verification:
- <test command>      → 47 passed, 0 failed, 2 skipped (skipped: live-API tests)
- <lint command>      → clean
- <typecheck command> → clean
- <build command>     → n/a for this project
```

## Red flags

If you are thinking:

- "Should work now" — RUN IT
- "I am confident" — RUN IT
- "It passed a few edits ago" — RUN IT AGAIN
- "Just this once" — NO, RUN IT

## Never

- Claim tests pass without running them in this session.
- Say "should work" in place of evidence.
- Trust an earlier run from before your last edit.
- Report a partial run as if it were the full suite.
- Weaken, skip, or delete a test to reach a green result. If a test is genuinely wrong, fix it and
  say plainly that you changed a test and why.

## If verification fails

Report the failure with its output, and say what you are doing about it. A failing step is a
result to report, not a reason to keep the work quiet — and it is never a reason to describe the
task as complete.

## Checklist

- [ ] Every applicable command run fresh, after the final edit
- [ ] Output read, not just exit codes
- [ ] Skips and filters accounted for
- [ ] Skipped steps named, with the reason
- [ ] Actual output pasted into the report
