# Run Tests

Run the project's tests and analyze failures. Argument: optional file path or test-name pattern.

## Resolve the command

Read the **Project Commands** table in `CLAUDE.md` (between the `claude:commands` markers):

- **No argument** → run `test`.
- **Argument given** → run `test-one`, substituting the argument for `{arg}`.
- **Table missing** → infer the runner from the manifest (`pyproject.toml`, `package.json`,
  `go.mod`, `Cargo.toml`, `Makefile`, …), state what you inferred, run it, and offer to write the
  table into `CLAUDE.md`.
- **`test` is `n/a`** → say the project declares no test command and stop. Do not invent one.

## Context

```bash
git diff --name-only HEAD~1
```

Use this only to orient — it shows what changed recently and therefore what is most likely to have
broken.

## If tests fail

1. Show the failure summary — actual output, not a paraphrase.
2. Read the failing test to understand what behaviour it asserts.
3. Read the code under test.
4. Explain the root cause. Do not skip to a fix; see the `debug` skill if the cause is not obvious
   from the trace.
5. Propose the fix, then apply it once the cause is established.

Never make a failing test pass by weakening its assertion, marking it skipped, or deleting it. If
the test itself is genuinely wrong, fix it and say explicitly that you changed a test and why.

## If tests pass

Report the actual counts, including skips — `47 passed, 2 skipped` is a different result from
`47 passed`, and the skips may be hiding the thing you were asked to verify. Add coverage if the
project produces it.
