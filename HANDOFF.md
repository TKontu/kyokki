# Handoff
Generated-UTC: 2026-09-14T06:00:00Z
Base-SHA: a8608cd

## Round delta
- #30 MVP-S2 merged: grouped stock view with stable sort.
- MVP-R0 spike run and passed (branch `docs/mvp-r0-extraction-spike`, PR open): results, working
  request and harness in `docs/vLLM_MANUAL_TEST.md` and `docs/spikes/r0_extraction_spike.py`.
  DEC-4 not needed.

## Active PRs and conflicts
- R0 docs PR only (docs + a standalone script). No conflicts with feature work.
- Worktree `C:/code/Kyokki-docs` still holds merged `docs/mvp-plan-review-amendments`; removable.

## Non-obvious decisions or blockers
- LLM gateway moved to llama-swap at `http://192.168.0.94:9292/v1` (deploy repo
  `Z:\llama-swap-deploy`; do not read its `.env`/`stack.env`). Only the RTX 3090
  `GPU-a8c640ca-...` is usable: no `*-split`, `pairNN.*`, `x2extract.*` models.
- Use `muse-glimmer`: always loaded by the operator's hot agent (no cold load); any other model
  evicts it and costs 3-4 min. It always reasons: `reasoning_strength` is only `xhigh|high|medium|low`
  (use `low`; no off switch). Stream long generations and keep
  output small: compact keys `{"p":[{"n","q","w"}]}`, `json_schema`, `max_tokens` 4096. ~42 s text,
  ~50 s image for a 49-product receipt; allow 60-90 s per call.
- Vision gets counts and weights right but misspells ~1 in 6 names on a clean image; text is exact.
  Primary path (MinerU OCR → text vs photo → vision) is decided in R4 once MinerU is back
  (offline until 2026-09-15). Strip trailing prices from names in the backend either way.
- Kyokki config is stale: `config.py`, `.env.example`, `stack.env.example` point at the dead
  `192.168.0.247:9003` with `LLM_MODEL=qwen3-8B`; `llm_extractor.py` sends `max_tokens: 16384`,
  no schema, full keys. R1/R4 replace this with the R0 request.
- DEC-1 left ml, l and kg out; confirm conversion factors before R1.
- Non-idempotent mutations need `retry: false` (providers retry mutations once).
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy on the homelab and confirm the iPad renders inventory.

## Next action
Merge the R0 docs PR. Code next: S4 (item edit sheet) or S3 (quick add). R1 is unblocked by R0 but
still needs the DEC-1 conversion ruling (`l→dl ×10`, `ml→dl ÷100`, `kg→g ×1000`?); once given, plan
R1 with both extraction paths wired to `muse-glimmer`.
