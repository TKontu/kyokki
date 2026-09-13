# Pipeline Review

Trace one entry point end to end and report real defects. Argument: the entry point — an HTTP route
(`GET /users/{id}`), a CLI command, a job or event consumer, a scheduled task.

## Context

Locate the layers this project actually has — do not assume a layering:

```bash
git ls-files | grep -iE "(route|handler|controller|endpoint|resolver|command|consumer)" | head -20
```

```bash
git ls-files | grep -iE "(service|usecase|domain|core|logic)" | head -20
```

```bash
git ls-files | grep -iE "(repo|repository|store|dao|db|client|gateway|adapter)" | head -20
```

## Trace the whole lifecycle

Follow the actual call chain, reading each function you pass through. Do not infer a step you have
not read.

1. **Entry** — how input arrives and is parsed. Which parameters are validated, and which are
   trusted. Authentication and authorization: is the check present, and is it before the work?
2. **Wiring** — what the entry point is handed, and how each collaborator is constructed. Shared
   state, connection pools, caches, module-level singletons — anything with a lifetime longer than
   one request is a place bugs hide.
3. **Logic** — the business rules, step by step. Input transformations, branch conditions, and the
   cases each branch does not handle.
4. **Data and I/O** — queries and their indexes, N+1 patterns, transaction boundaries (what is
   inside, what escapes), external calls and whether they have timeouts, retries, and idempotency.
5. **Exit** — does the declared output contract match what is actually returned on every path?
   Error responses, status codes, and what leaks into them.

Cross-cutting, at every layer: what happens on failure, what is logged (and whether it leaks
secrets or personal data), and what happens under concurrent execution.

## Classify each finding

- **🔴 Error** — will fail. An unhandled exception, a type mismatch, a missing await, a null
  dereference on a reachable path.
- **🟠 Bug** — runs, but does the wrong thing. Wrong logic, lost updates, a race, a transaction
  that commits partial work.
- **🟡 Issue** — bites under specific conditions. An unindexed query that is fine at current scale,
  a missing timeout, an edge case in input handling.

Every finding needs `file:line` and a concrete failure scenario: the input or state that triggers
it, and what goes wrong. If you cannot write that scenario, it is a theoretical concern — leave it
out. A short report of real defects is worth more than a long one padded with speculation.

## Output

Write `docs/reviews/pipeline-{name}.md` (create the directory if needed):

```markdown
# Pipeline Review: {entry point}

Reviewed at {SHA}.

## Flow
handler.ext:fn → wiring.ext:dep → service.ext:method → store.ext:query

## Critical (must fix)
- [ ] path/file.ext:123 — what is wrong, and the input that triggers it

## Important (should fix)
- [ ] path/file.ext:456 — what is wrong, and when it bites

## Minor
- [ ] path/file.ext:789 — what is wrong

## Verified sound
<Only the load-bearing things you actually checked and found correct — one line each.
Not a list of everything you read.>
```

Do not record "all looks good" items as findings.
