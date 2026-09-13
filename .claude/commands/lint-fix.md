# Lint and Fix

Autofix what the linter can, format, then resolve what is left by hand.

## Resolve the commands

From the **Project Commands** table in `CLAUDE.md`: `lint-fix`, `format`, `lint`. Any key that is
absent or `n/a` is skipped and reported as skipped — never substitute a linter the project does not
use.

## Sequence

1. `lint-fix` — apply the automatic fixes
2. `format` — format the code
3. `lint` — report what still needs a human decision

## For each remaining issue

- Name the rule and explain what it is actually complaining about.
- Apply the fix.
- If a rule is wrong for this codebase, say so and suggest configuring an exception in the linter
  config — do not scatter inline suppressions to reach a clean run.

## Verify

Re-run `lint` after your manual fixes, then summarize:

```bash
git diff --stat
```

Report the actual final linter output, not "should be clean now".
