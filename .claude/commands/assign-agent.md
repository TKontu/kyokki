# Assign an executor

Produce one bounded, decision-complete prompt for an isolated executor. Use this for a single task
outside a round; use `/plan-round` for a parallel batch.

1. Follow `CLAUDE.md` and `docs/conventions.md` if it exists. Start from a fast-forwarded
   integration branch and record its full SHA — the executor cuts from that commit.

2. Confirm the item is `ready` in `docs/backlog.md` and that its stated owned paths match the
   source. Verify; do not take the row's word for it.

3. Write the spec from `.claude/templates/TODO-agent-template.md`. It must stand alone: the
   executor's workspace has none of your context, so every scope link, path, and already-made
   decision goes in the spec itself.

4. Resolve the scoped test and lint commands from the **Project Commands** table in `CLAUDE.md`
   and write the concrete commands into the spec.

5. Check it against the completeness bar in `.claude/templates/CLAUDE-orchestrator.md`: could you
   build exactly the right thing from this spec and nothing else?

6. Hand the operator the prompt path and tell them to paste it into one fresh executor session
   using `.claude/templates/CLAUDE-executor.md` as that workspace's `CLAUDE.md`. Do not launch the
   executor yourself.
