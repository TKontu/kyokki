# Handoff
Generated-UTC: 2026-10-02T04:20:00Z
Base-SHA: 20fb183a7010f9dd510bba0b4be7d17f4cab1609

## Round delta
- **Round 2026-10-01-1:** #139 (AG4 skill + CLI receipts), #140 (live updates over SSE), #141 (Q38 re-analyse + Q39 printed line) and #143 (Q37 snapping) are merged by the operator (2026-10-02), **not deployed**. #142 (Q18-G2 generated icons) is open, in its fix pass.
- **Round 2026-10-02-1** is dispatched from `1520506` while the above were open. Its lanes:
  - A1: shopping screen;
  - A2: waste rate and trend;
  - A3: agent discard-expired and the Q24 ordering;
  - A4: undo correction direction;
  - A5: store chain OCR tolerance. A5 is #144, under review.
- Outcomes and follow-ups are in `docs/TODO.md`, in the round block after the Q37-Q39 friction log. The round logs are `.rounds/2026-10-01-1/round.md` and `.rounds/2026-10-02-1/round.md`.

## Active PRs and conflicts
- #142: must merge `main` (now 20fb183); it owns the only new Alembic head (on `fbf2c08da52d`).
- Round 2 lanes cut from `1520506` and must merge `main` before merge.
  - A4 edits `schemas/inventory_item.py` and `frontend/types/inventory.ts`, in the undo-step region only. #142 edits the icon fields in the same files. The hunks are disjoint.

## Non-obvious decisions or blockers
- **Q37 (#143) is partial by design.** `c2.muse-glimmer` still keeps some snaps, but they now arrive unverified.
  - **Q37b (high, next):** a rejected snap can re-attach at confirm through `product_for_name`'s canonical fallback (`receipt_confirm.py:137`). It needs `receipt_processing.py` and `receipt_confirm.py`, both on `main` now.
- **Ruling:** a processing form (mince vs fillet) is a different product. MVP-R2's "cut" means equivalent retail cuts.
- **#140:** `Cache-Control: no-transform` on `/api/events` is load-bearing; Next's gzip otherwise buffers the stream.
- **#142 Regenerate ruling:** allowed on `cleared` products, refused for exact/cook emoji; a rename uses the automatic gate.
- **Operator actions:**
  - the live ComfyUI check for #142: allow `ssh -N -L 19292:127.0.0.1:9292 sandbox-host` and an agent runs it, or run it on the workstation;
  - in production, remove the aliases `KARTANON KALKKUNALEIKE → Ham` and `VALIO VOI NORMAALISUOLAI → Spread`, and rename or re-categorise "Dip";
  - after #144 merges, run `scripts/rekey_store_chains.py` (dry run first);
  - `LLM_MAX_TOKENS`;
  - "Re-estimate all";
  - the AG7 Hermes run.
- **Environment:**
  - `backend/.venv/bin` is broken; use `/usr/bin/python3.12` with the venv's site-packages (see the preamble).
  - The agent is denied `gh pr merge` and force-push; the operator merges.
  - Executors run on Sonnet (operator). Its session limit stopped four agents once; re-run any lens that dies.
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.

## Next action
Finish round 2026-10-02-1: review #144 and the four lanes still running, verify #142's fix pass, and have the operator merge. Then reconcile and plan the next round with Q37b first.
