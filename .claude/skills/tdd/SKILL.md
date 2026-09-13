---
name: tdd
description: Use when implementing any feature or bugfix - write test first, watch it fail, then implement
---

# Test-Driven Development

## The Rule

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

## Resolve the commands first

Read the **Project Commands** table in `CLAUDE.md` (between the `claude:commands` markers) and use
`test-one` for the cycle, `test` for the final check. Never assume a runner. If the table is
missing, infer the runner from the project manifest, say what you inferred, and use that.

Throughout this skill, `<test-one>` means "that project's single-test command applied to the file
you are working on".

## Red-Green-Refactor

### RED — write the failing test

Write one test for one behaviour. Name it after the behaviour, not the function:

```
test: rejects an empty email with "Email required"
```

Run it:

```bash
<test-one>
```

**Watch it fail.** Then confirm it failed for the *right* reason — the behaviour is missing, not a
typo, a bad import, or a fixture that never loaded. A test that errors before reaching your
assertion has told you nothing.

### GREEN — minimal code

Write the simplest thing that makes the test pass. Not the general solution — the specific one.
Generality arrives when a second test demands it.

```bash
<test-one>
```

All pass.

### REFACTOR

Clean up only if there is something to clean. Keep the tests green while you do it — run them
after each structural change, not once at the end.

### Repeat

Next failing test for the next behaviour.

## Verification

The cycle is only real if you observed each transition:

- [ ] Test written before the implementation
- [ ] Watched it fail, and read the failure
- [ ] Failure was the missing behaviour, not a broken test
- [ ] Minimal implementation
- [ ] Watched it pass
- [ ] Ran the surrounding tests — nothing else broke

## Anti-patterns

| Bad | Good |
| --- | --- |
| Write code, then a test for it | Write the test, watch it fail, then the code |
| "I will test it after" | The test first is what proves the code works |
| Several behaviours in one test | One behaviour per test |
| Test passes on the first run | It must fail first, or it proves nothing |
| Test asserts what the code does | Test asserts what the code *should* do |
| Loosening the assertion to get green | Fix the code, or fix a genuinely wrong test — and say so |

## When a test is hard to write

That is information, not an obstacle. A behaviour that is hard to test usually has a dependency
that should be injected, a side effect that should be returned, or a function doing two jobs. Fix
the shape rather than reaching for elaborate mocking.
