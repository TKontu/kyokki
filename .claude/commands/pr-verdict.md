# PR Verdict

Run a review panel on one PR and post the verdict as a PR comment. Argument: `<pr-number>`.

**Advisory only.** Never block, never merge, never push fixes from this command. The operator
remains the only merger.

## 1. Idempotency

```bash
gh pr view <n> --json comments -q '.comments[].body' | grep -c "pr-verdict"
```

If a comment already contains `<!-- pr-verdict -->`, stop and report that the verdict exists.
Re-run only on explicit operator request.

## 2. Gather — do not review it yourself

Collect, without forming an opinion:

- The changed-file list: `gh pr diff <n> --name-only`
- The owning backlog row and its detail section — resolve the item id from the PR title or branch
- The architecture or design docs that row names

**Do not read the PR body yet.** It goes only to the claims lens, so the other lenses cannot be
anchored by the author's framing.

## 3. Tier

- Diff touches **executable code** — source, tests, scripts, migrations, build config → **full**:
  lenses 1–5.
- Any other diff — docs, prompts, skills, CI config → **light**: lenses 1–2.

Every diff gets a tier. The refuter pass applies to both.

## 4. Panel

Spawn every applicable lens as a **parallel fresh-context subagent** (Agent tool,
`general-purpose`, all in one message). Each brief carries: the PR number, the changed-file list,
the paths of the owning row and the canonical docs, and the instruction to fetch the diff itself
(`gh pr diff <n>`).

**Never include the desired outcome, the author's rationale, or another lens's brief.** A lens told
what to conclude will confirm it.

1. **claims** — fetch the PR body. Extract every factual claim it makes (a byte-identical move, "no
   remaining callers", a coverage number, a gate that was run). Verify each at source or by running
   the named command. Return a held/refuted table with evidence.

2. **conformance** — any rule, gate, or decision text restated **in the diff**: diff it word by word
   against the original document. Drift in either direction is a finding. (Body restatements are
   the claims lens's job — this lens never sees the body.) If the project has a backlog or docs
   validator, run it.

3. **correctness** — hunt defects in the diff. Every finding needs `file:line` and a concrete
   failure scenario. For a move or relocation PR, compare each moved body old-vs-new token by
   token (move purity).

4. **scope** — compare the diff against the owning row's authorized scope. Flag files or edits
   outside it, and any design change not backed by a recorded decision.

5. **integration-path** — when the change touches a pipeline or a configurable path: verify that
   the tests and fixtures the PR relies on exercise the **production** configuration, not a dead
   branch or a test-only default.

## 5. Refuter pass

A finding independently reported by **≥2 lenses**, or one you re-executed and reproduced at source
yourself, is **CONFIRMED without a refuter**. The pass exists to kill false positives, not to
re-prove corroborated facts.

For the rest — singletons and interpretive findings — spawn one fresh subagent per finding, briefed
to *refute it at source*. Verdicts:

- **CONFIRMED** — verified or reproduced
- **PLAUSIBLE** — unrefuted but unproven
- refuted findings are **dropped**

Assign the verdict before the severity.

## 6. Post one comment

```bash
gh pr comment <n> --body-file <file>
```

First line `<!-- pr-verdict -->`, then: the tier, the claims table, the findings (verdict,
severity, `file:line`, one line each), a one-line conformance statement, and a recommendation —
**merge** / **fix-first** / **escalate**.

Report the counts back to the session so `/reconcile` can record review calibration.
