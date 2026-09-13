# CLAUDE.md

> Copy this to your project root as `CLAUDE.md`, fill in every `<...>`, then append a stack profile
> from `.claude/templates/profiles/`. Keep the whole file under ~2–3k tokens — it is loaded on every
> message.

## What this project is

<One or two sentences: what it does and who it is for.>

**Stack:** <language + runtime version, framework, datastore, anything else load-bearing>
**Profile:** <`.claude/templates/profiles/<name>.md`, or "none">

## Project Commands

Every command in `.claude/commands/` resolves its tooling from this table. Fill in what exists;
write `n/a` for what does not, and commands will skip that step rather than guess. `{arg}` is
replaced with the user's argument.

<!-- claude:commands -->
| Key       | Command |
| --------- | ------- |
| install   | <install dependencies> |
| test      | <run the full suite> |
| test-one  | <run one file or pattern, using {arg}> |
| lint      | <report lint problems> |
| lint-fix  | <autofix lint problems> |
| format    | <format code> |
| typecheck | <static type check, or n/a> |
| run       | <start the app locally, or n/a> |
| build     | <produce a build artifact, or n/a> |
<!-- /claude:commands -->

## Repository layout

```
<tree of the directories that matter — where source, tests, config, and migrations live>
```

Where things go:

- **Source:** `<dir>`
- **Tests:** `<dir>` — mirror the source layout
- **Config:** `<dir>`
- **Docs / backlog:** `docs/backlog.md` is the source of truth for planned work

## Code style

<Prefer pointing at the enforcing config over prose — a linter rule beats a paragraph.>

- Formatting and lint are enforced by `<tool>`; its config lives in `<file>`. Do not hand-format
  around it.
- **Naming:** <the conventions for functions, types, constants, and private members>
- **Imports:** <ordering and grouping rules, or the tool that enforces them>
- **Types:** <where annotations are required, and the strictness level>
- **Docs/comments:** <the docstring or comment style, and when one is required>

## Architecture conventions

<The handful of rules a newcomer would otherwise get wrong. Examples of the *kind* of rule that
belongs here — replace with your own:>

- **Layering:** <which layer may call which; what must never reach across>
- **Dependency wiring:** <how a component receives its collaborators>
- **Configuration:** read from the environment; never hardcode secrets. Precedence is
  defaults < environment < explicit arguments.
- **Errors:** <the project's error type/hierarchy, and where external errors get converted>
- **Logging:** <the logger, the structured-field convention, and what must never be logged>
- **Feature flags:** <how a change ships dark, if that applies>

## Testing

- Every behaviour change lands with a test. See the `tdd` skill for the cycle.
- **Layout:** <naming convention and directory for test files>
- **Fixtures/factories:** <where shared setup lives>
- **Markers/tags:** <how slow, integration, or live tests are separated and how to run them>
- Do not weaken or delete a failing test to make a change land — fix the change, or record why the
  test was wrong.

## Definition of done

- [ ] Tests written and passing (`test` or `test-one` from the table above)
- [ ] `lint` clean and `format` applied
- [ ] `typecheck` clean, where the project has one
- [ ] No secrets, credentials, or personal data added
- [ ] Docs and `docs/backlog.md` updated for anything a reader would otherwise get wrong

## Pull requests

```markdown
## Summary
What changed and why.

## Changes
- <change and its reason>

## Testing
- <exact commands run, with their actual output>

## Checklist
- [ ] Tests added/updated
- [ ] Lint/format/typecheck clean
- [ ] Breaking changes documented

## Related
<backlog ID(s) and issue links>
```

---

<!-- Append your stack profile below this line. -->
