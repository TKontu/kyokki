# Handoff
Generated-UTC: 2026-10-01T06:00:00Z
Base-SHA: c4406272c6bce74930df7b07a8e8e3883b053f7d

## Round delta
- Round 2026-09-30-1 is merged and reconciled. **It is not deployed.**
- PRs:
  - #133 GW-1 gateway key;
  - #134 #130 follow-ups;
  - #135 the Q18-G1 ComfyUI client and style trial;
  - #136 the Q26/Q28 receipt audit;
  - #137 the Q18-B exact emoji.
- Results and follow-ups are in `docs/TODO.md`, in the round block above Q28.
- Every PR had a verdict panel (all fix-first) and a fix pass that the planner checked at source.

## Active PRs and conflicts
- This reconcile's docs PR only.

## Non-obvious decisions or blockers
- **`LLM_API_KEY` is set in the stack (operator, 2026-10-01).** It is required:
  - The llama-swap gateway has required a bearer key since 2026-09-30.
  - The prod compose now uses `${LLM_API_KEY:?}`, so the stack refuses to start without it, even for
    `logs` and `down`.
  - In the local `.env`, the key is `LLAMASWAP_API_KEY`; the code reads `LLM_API_KEY`.
- **Two new Alembic revisions:** `f1a2b3c4d5e6`, then `fbf2c08da52d`.
- **Then run `backfill_emoji`** (`--dry-run` first) in `kyokki-api`.
- **Q18-G2 is blocked on the operator.**
  - ComfyUI (`a4.comfyui` on 192.168.0.94) is loopback-only, and the edge returns 403 from the LAN.
  - The Kyokki server needs a route: a Caddy allow rule, the media-gateway on `:8480`, or co-location.
  - The style is ruled: **"Flat. No faces"**. The flat recheck had no faces but was only 4/10 clean,
    and Quark has never rendered.
  - The operator's GPU-box rules and the verified graph are in `.rounds/2026-09-30-1/specs/A2.md`.
- **Environment:**
  - `backend/.venv/bin/*` are XSym stubs, so the interpreter fails. Run
    `/usr/bin/python3.12` with `PYTHONPATH=<pydeps>:backend/.venv/lib/python3.12/site-packages`, plus
    `ruff==0.12.12` and `defusedxml` via `pip --target` (see the round preamble).
  - `git push --force` is blocked, so lanes merge `main` instead of rebasing.
  - Merges and permission edits are the operator's; `gh pr merge` is denied to the agent.
  - Panels ran on Sonnet at the operator's request ("Use sonnet").
- **Still pending from earlier:**
  - `LLM_MAX_TOKENS` (16384 recommended);
  - clearing the rejected SVG icons;
  - "Re-estimate all".
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
The operator deploys round 2026-09-30-1 (`LLM_API_KEY` is already set; run `alembic upgrade head` and `backfill_emoji`)
and decides how the Kyokki server reaches ComfyUI. Then run `/plan-round` for Q18-G2, using
`docs/TODO.md` (Q18 follow-ups) and `docs/spikes/Q18_icon_styles.md`.
