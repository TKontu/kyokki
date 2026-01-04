# Claude Code Best Practices

## Context Management
- **Start fresh often** - New conversation per topic, long contexts reduce effectiveness
- **Handoff docs** - Summarize progress to a `.md` file before `/clear` to preserve continuity
- **Break down problems** - Divide complex tasks into smaller subtasks until each is solvable

## Workflow
- **Write tests first** - TDD lets Claude verify its own work autonomously
- **Use `/compact`** - Compress context when conversation gets long
- **Background tasks** - Run long operations in background, continue other work

## Terminal
- **Aliases** - `alias c='claude'` `alias ch='claude --chrome'`
- **`realpath`** - Use for absolute paths: `realpath ./src/file.py`
- **Containers** - Use Docker for risky/destructive operations

## Git
- **Draft PRs** - Safer than direct PRs: `gh pr create --draft`
- **Let Claude commit** - It writes good commit messages

## CLAUDE.md
- **Keep it simple** - Every token in CLAUDE.md is loaded every message
- **~2-3k tokens max** - More = less context for actual work
- **Project-specific only** - Don't duplicate general knowledge

## Slash Commands
- `/clear` - Start fresh conversation
- `/compact` - Compress context
- `/cost` - Check token usage
- Custom commands in `.claude/commands/` for repeated workflows

## Debugging
- **Screenshots** - Paste images directly for UI issues
- **Logs** - Provide error output, not just "it failed"
- **Reproduce** - Give Claude a way to verify fixes (tests, scripts)
