# Stack profiles

A profile is the stack-specific half of a project's `CLAUDE.md`. The templates in
`.claude/templates/` are language-agnostic; a profile fills in the concrete toolchain, idioms, and
patterns for one stack.

## Using one

1. Copy `../CLAUDE-default.md` to the project root as `CLAUDE.md`.
2. Paste the profile's **Project Commands** rows into the `claude:commands` table.
3. Append the rest of the profile below the marker at the bottom of `CLAUDE.md`.
4. Delete what does not apply. A profile is a starting point, not a contract — the only contract
   is the Project Commands table.
5. If the profile has a **Settings** section, merge those permissions and hooks into
   `.claude/settings.json`.

## Writing one

Copy an existing profile and replace its contents. A good profile has:

| Section | Contains |
| --- | --- |
| **Project Commands** | The rows to paste into the `claude:commands` table. Required. |
| **Toolchain config** | The lint/format/type config, as it should appear in the manifest. |
| **Code style** | Naming, imports, docs, types — the conventions the linter cannot enforce. |
| **Framework patterns** | The 3–5 idioms a newcomer would otherwise get wrong. |
| **Errors & logging** | The error hierarchy and the structured-logging convention. |
| **Testing** | Fixture, factory, and test-layout patterns. |
| **Debugging** | The debugger entry point and the useful test-runner flags. |
| **Settings** | Permissions and hooks to merge into `.claude/settings.json`. |

Keep it to what is *load-bearing*. A profile that restates the language's tutorial burns context on
every message; one that names the project's actual layering rule earns its place.

**Two rules for every profile:**

- Nothing in it may name a specific project, repository, service, or internal identifier. If an
  example needs a domain, invent a neutral one (`User`, `Order`, `Item`).
- The Project Commands rows must be runnable as written, from the repository root.

## Available

| Profile | Stack |
| --- | --- |
| `python-fastapi.md` | Python 3.12+, FastAPI, Ruff, pytest, mypy, structlog |
| `node-typescript.md` | Node 20+, TypeScript, ESLint, Prettier, Vitest |
| `go.md` | Go 1.22+, standard toolchain, `golangci-lint`, table-driven tests |

To add Rust, Java, C#, or anything else: copy the closest of these, keep the section headings, and
replace the contents.
