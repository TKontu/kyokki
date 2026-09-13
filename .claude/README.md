# Claude Code scaffold kit

A portable set of commands, skills, and templates for driving a project with Claude Code —
including a multi-agent "round" workflow. **Nothing here is tied to a particular project or
language.** Anything stack-specific lives in a *profile* you pick per project.

## Install into a new project

```bash
cp -r /path/to/this/.claude  <new-project>/.claude
cp -r /path/to/this/cheatsheets <new-project>/cheatsheets   # optional
cd <new-project>
```

For a brand-new Python project, `starters/python/` has a matching `pyproject.toml` and
`.env.example` to copy to the root as well.

Then, in that project:

1. Copy `.claude/templates/CLAUDE-default.md` to `./CLAUDE.md`.
2. Fill in the **Project Commands** table (below). This is the one thing every command depends on.
3. Append a stack profile from `.claude/templates/profiles/` (or write your own — see
   `profiles/README.md`).
4. Optional, only for the round workflow: run `/takeoff`, which bootstraps `docs/backlog.md`
   and `docs/conventions.md` if they are missing.

## The two contracts

Every command in this kit is written against these two contracts and nothing else. Honour them and
the whole kit works on any repo, in any language.

### Contract 1 — Project Commands

`CLAUDE.md` carries a fenced table between the `claude:commands` markers. Commands read this table
instead of assuming a toolchain:

```markdown
<!-- claude:commands -->
| Key       | Command                          |
| --------- | -------------------------------- |
| install   | <how to install deps>            |
| test      | <run the whole suite>            |
| test-one  | <run one file/pattern; use {arg}>|
| lint      | <report lint problems>           |
| lint-fix  | <autofix lint problems>          |
| format    | <format code>                    |
| typecheck | <static type check>              |
| run       | <start the app locally>          |
| build     | <produce a build artifact>       |
<!-- /claude:commands -->
```

Rules a command must follow:

- **Resolve, don't assume.** Read the key you need from this table. Never hardcode `pytest`,
  `npm test`, `go test`, `ruff`, `eslint`, …
- **Absent or `n/a` means skip.** Say in the report which step was skipped and why — never
  substitute a guess, and never invent the tool.
- **`{arg}` is substituted** with the user's argument in `test-one` (and any other key that
  declares it).
- **No table?** Infer commands once from the manifest (`pyproject.toml`, `package.json`,
  `go.mod`, `Cargo.toml`, `Makefile`, …), state the inference, and offer to write the table.

### Contract 2 — Backlog

`docs/backlog.md` is the single source of truth for what is planned, active, and done. Format is in
`.claude/templates/backlog-template.md`. Minimum a command may rely on:

- A markdown table of items, each with an **ID** (`<TRACK>-<n>`, tracks are the project's own),
  a **status** (`ready` / `active` / `blocked` / `done`), and a one-line **title**.
- A `## Current frontier` section naming what to work on next.

Commands that write to the backlog append; they never rewrite history.

## What is here

```
.claude/
├── commands/          slash commands (see tiers below)
├── skills/            debug, tdd, verify + optional gitnexus-* graph skills
├── templates/         CLAUDE.md, TODO, backlog, round, handoff templates
│   └── profiles/      stack-specific add-ons (python-fastapi, node-typescript, go, …)
└── settings.json      permissions + hooks (stack-neutral; profiles add to it)
```

### Command tiers

**Everyday** — work on any repo with no setup beyond Contract 1:

| Command | Purpose |
| --- | --- |
| `/test` | Run tests, diagnose failures |
| `/lint-fix` | Lint, autofix, format, report what is left |
| `/review` | Review the working diff |
| `/secrets-check` | Scan staged changes for credentials |
| `/commit-push-pr` | Commit, push, open a PR |
| `/update-todos` | Sync the backlog with what this session did |
| `/new-endpoint` | Scaffold a new entry point (route/handler/command) |
| `/pipeline-review` | Trace one entry point end to end and report defects |

**Rounds** — the multi-agent workflow; needs Contract 2, which `/takeoff` bootstraps:

| Command | Purpose |
| --- | --- |
| `/takeoff` | Orient a fresh session; bootstrap missing scaffolding |
| `/status` | Read-only backlog tally + feasibility assessment |
| `/plan-round` | Pick N parallel-safe items, write the round, emit executor prompts |
| `/assign-agent` | Emit one executor prompt outside a round |
| `/review-round` | Review every PR in the round |
| `/pr-verdict` | Run the review panel on one PR, post the verdict |
| `/merge-round` | Merge the round's ready PRs |
| `/reconcile` | Record results, re-point the frontier, write the handoff |
| `/handoff` | Write the bounded delta for the next session |
| `/orchestrate` | The whole loop, end to end |

Everything the round workflow needs is plain files — a round directory and markdown. There are no
required helper scripts. If a project *does* add validation scripts, declare them in
`docs/conventions.md` under **Round tooling** and the commands will use them.
