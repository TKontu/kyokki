# New Entry Point

Scaffold a new entry point following the project's existing patterns. Argument: a description of
what to add — `GET /users/{id}`, `a CLI subcommand "export"`, `a queue consumer for order.created`,
`a gRPC method GetUser`.

## Context

Find how this project already does it, before writing anything:

```bash
git ls-files | grep -iE "(route|handler|controller|endpoint|resolver|command|consumer|api)" | head -20
```

```bash
git ls-files | grep -iE "(schema|model|dto|type|contract|proto)" | head -20
```

```bash
git ls-files | grep -iE "(^|/)(test|tests|spec|__tests__)/" | head -20
```

Read two or three of the closest existing examples in full. **The nearest neighbour in this
codebase outranks any pattern in a profile or in your own habits** — including its registration
mechanism, its error handling, and its file naming.

## Produce

1. **The handler** — placed and named the way its neighbours are.
   - Same validation approach for input as the existing ones
   - Same error signalling — the project's error types and status mapping
   - Same dependency wiring; do not introduce a new construction style
   - Registered wherever the project registers these (a router, a registry, a decorator, a config
     entry) — a handler nobody routes to is not done

2. **Input and output contracts** — request/response models, argument parsing, or message schema,
   in the project's existing form, in the file its neighbours live in.

3. **Tests** — mirroring the structure of the existing tests for this kind of entry point:
   - The success path
   - The failure paths this entry point can actually produce (not found, invalid input,
     unauthorized — whichever apply)
   - Write the test first; see the `tdd` skill

4. **Anything the project couples to an entry point** — an OpenAPI or schema regeneration, a
   permissions entry, a rate-limit rule, a changelog line. Check a recent commit that added one and
   copy what it touched.

## Verify

Run the scoped test command from the **Project Commands** table (`test-one` on your new test file)
and the `lint` command on the files you created. Report actual output.

## Do not

- Invent a layering the project does not have.
- Add authentication, caching, or pagination that was not asked for and that neighbours do not
  have.
- Leave the entry point unregistered or untested.
