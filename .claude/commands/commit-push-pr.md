# Commit, Push, and Create PR

Commit staged changes, push, and open a pull request.

## Context

```bash
git status --short
```

```bash
git diff --cached --stat
```

```bash
git log --oneline -5
```

```bash
git branch --show-current
```

## Instructions

1. **Secrets check** — run the `/secrets-check` scan over the staged changes. If a real secret is
   found: STOP, report it, and do not commit.

2. **Review the staged changes.** If nothing is staged, say so and suggest the `git add` commands
   for the relevant modified files — do not stage everything on the user's behalf.

3. **Check the branch.** If you are on the default branch (`main`/`master`), create a branch first;
   never commit directly to it.

4. **Write the commit message** — conventional commits: `feat`, `fix`, `refactor`, `docs`, `test`,
   `chore`, `perf`, `build`, `ci`. Subject in the imperative under ~72 characters. The body says
   *why*, not what — the diff already says what.

5. **Commit and push**, setting upstream on the first push of a branch.

6. **Open the PR** with:
   - A title summarizing the change
   - A body: what changed and why, how it was verified (actual command output), and any breaking
     changes
   - Links to the backlog ID or issues referenced in the commits
   - Use the project's PR template if one exists in `.github/`

7. **Optional review pass** — if the project uses `/pr-verdict`, offer to run it on the new PR
   number. Do not run it unasked; it spawns a panel of subagents.

Draft PRs (`gh pr create --draft`) are the safer default for work that is not yet final.
