# Handoff
Generated-UTC: 2026-09-27T00:00:00Z
Base-SHA: 693f88dfe020dc8c3256c8af646344ae5bcad846

## Round delta
- Round 2026-09-26-9 is merged, reconciled and **not deployed**:
  - #119 Q24: corrected dates teach the product;
  - #121 Q18 step 1: model-drawn product icons (migration `e4b8c1d7a236`);
  - #120: layout pass (Q20, Q23, Q22 wording, Q25);
  - docs #117, #118.
- Results, rulings and follow-ups are in `docs/TODO.md`, under the Q20-Q28 friction section.
- Q27 (receipt lines lost without a trace) and Q28 (receipts not auditable) are logged. They are untriaged.

## Active PRs and conflicts
- Only this reconcile's docs PR (`docs/reconcile-2026-09-26-9`).

## Non-obvious decisions or blockers
- **Rulings made at review:**
  - The Q24 rule: ignore dates on or before purchase; the latest date wins for 1-2 dates, and the median of the last 5 for 3 or more.
  - A thawed item never teaches.
  - The put-back undo always reads "Put back".
  - `icon_status='cleared'` keeps the cook's emoji choice.
- **`ICON_MODEL` defaults to `c2.qwen3.8-27b`** (quality: about 17/20 recognisable, against about 4/20 for muse-glimmer). It shares the c2 GPU with the receipt model; switching back costs 5-10 s.
- **The shared `backend/.venv` lacks `defusedxml`** (new in `requirements.txt`). Backend tests here need `pip install -r backend/requirements.txt` into it first.
- **Q26 needs a migration.** The next round's alembic head belongs to whichever lane takes Q26 or Q28.
- **Environment carried over:**
  - Merges are the operator's.
  - At most about three verdict panels at a time; panels must not draft lens reports themselves.
  - Never symlink the shared `frontend/node_modules`; it is empty here, so run `npm ci` before frontend work.
  - Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`.
- **Still awaiting the operator:**
  - the homelab API address and a read token, for the Q27 triage;
  - the #105 `model`-marking nod.

## Next action
Deploy (`docs/DEPLOY.md`, then `alembic upgrade head`) and run `backend/scripts/backfill_icons.py`.
Then triage Q27 from `GET /api/receipts/{id}`, and `/plan-round` for Q26 + Q28 (+ the Q27 fix).
