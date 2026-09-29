# Handoff
Generated-UTC: 2026-09-27T16:00:00Z
Base-SHA: 378aadb82e5e50d348170d012a50780a0a0e38e4

## Round delta
- Round 2026-09-27-3 is merged, **deployed** and reconciled:
  - #131: Q27 hardening;
  - #129: the Q18 exact-emoji trial (a spike);
  - #130: Q29-Q36 fridge look and shell.
- Results and follow-ups are in `docs/TODO.md`, in the round block under Q27/Q28.
- #131 went in after a large fix pass without a second review panel.

## Active PRs and conflicts
- This reconcile's docs PR only.

## Non-obvious decisions or blockers
- **Icons.** The LLM-drawn SVGs are rejected.
  - An emoji is used only when there is an **exact** Apple emoji, decided per product under the
    operator's rule "It needs to be precise, so it doesn't require cognitive effort".
  - The ruled table (109 exact, 58 gap with icon briefs, 24 non-food with no icon) is in
    `docs/spikes/Q18_exact_emoji.md`.
  - The gaps will be generated through ComfyUI behind llama-swap. **Wait for the operator's
    ComfyUI details before planning that lane.** The emoji-table build can go first.
- **Receipts.** Any country and language must work, with no hardcoded formats in the core. Country
  parsers are optional profiles only (`fi` today). Multi-line items must always work.
- **Pending operator decision:** `LLM_MAX_TOKENS`, 8192 → 16384 recommended. Some long first reads
  are truncated.
- **Watch:** a read occasionally fills almost no categories. Real receipts now store the raw model
  answer; ask the operator for the receipt id when it happens.
- **Hardware:** 2×3090 on the gateway (muse-glimmer plus one co-hosted model) and 3× A2000 12 GB.
- **Environment:**
  - Merges are the operator's.
  - Verdict panels must not draft their own lens reports; at most 6 agents at a time.
  - Executors cannot message the orchestrator; they report at the end.
  - Use fake card and phone strings in tests; realistic ones tripped an output filter twice.
  - Never symlink `frontend/node_modules`.
  - The shared venv lacks `defusedxml`.
  - Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
`/plan-round`: the Q18 emoji build (a per-product table seeded from the rulings, skipping non-food)
plus Q26/Q28 (receipt provenance and audit view) and the #130 follow-ups. Add the ComfyUI gap lane
once the operator shares the llama-swap details.
