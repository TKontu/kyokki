# Review Changes

Review the current working changes before committing.

## Context

```bash
git status --short
```

```bash
git diff --stat
```

```bash
git diff
```

If the diff is large, review it in file groups rather than skimming all of it — a skimmed review
that reports nothing is worse than no review, because it manufactures false confidence.

## Review for

1. **Correctness** — logic errors, off-by-one, null/empty handling, error paths that swallow
   failures, concurrency and ordering assumptions, resource cleanup.
2. **Security** — injection through unvalidated input, hardcoded credentials, path traversal,
   unsafe deserialization, secrets in logs, missing authorization checks.
3. **Contracts** — does the change match what its callers assume? Any signature, schema, or
   serialized-format change that breaks an existing consumer?
4. **Tests** — is the changed behaviour actually covered? Would the new test fail if the change
   were reverted? Watch for tests weakened to accommodate the change.
5. **Conventions** — does it match `CLAUDE.md` and the surrounding code's idiom, naming, and
   error handling?
6. **Simplification** — duplicated logic that already exists elsewhere, indirection that earns
   nothing, dead code left behind.

## Output

Every finding needs `file:line` and a concrete failure — the input or state that triggers it, and
what goes wrong. A finding you cannot make concrete is a question, so ask it as one.

- 🔴 **Critical** — must fix before merge
- 🟡 **Warning** — should fix; explain the condition under which it bites
- 🟢 **Suggestion** — improvement, not a defect

Prefer few high-confidence findings over a long speculative list. If the changes look good, say so
plainly and name what you checked.
