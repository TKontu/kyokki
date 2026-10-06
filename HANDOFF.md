# Handoff
Generated-UTC: 2026-10-05T05:29:40Z
Base-SHA: d6ec2a797c2213031950301a32dd67b59b9b53cc

## Round delta
- Round 2026-10-04-2 merged 2026-10-05 (#182 to #186), **not deployed**. No migration, no setting.
  - #185: the Android share target, `POST /api/receipts/share` (303 to the receipt, the list, or
    `/scan?shared=failed`);
  - #184: several receipts per upload on `/scan`;
  - #183: the `app.services.{units,item_status,storage,product_names}` shims are deleted (use
    `app.domain.*`, `app.crud.product_name`);
  - #186: the flaky display-name test fixed (stubs answered by position).
- Core-loop audit (operator ask): new backlog items CL1 to CL6 in `docs/TODO.md` (round block
  2026-10-04-2). Log: `.rounds/2026-10-04-2/round.md`.

## Active PRs and conflicts
- Only this reconcile.

## Non-obvious decisions or blockers
- **The planner cannot merge** (`gh pr merge` is denied); the operator merges each round.
- Telegram is the operator's main input. CL1 (confirm from the bot), CL2 (restock clears shopping)
  and CL3 (bot shopping/consume) are the highest-value gaps. CL1 and CL3 both edit
  `backend/app/telegram_bot/**`, so they cannot share a round unless the module is split explicitly.
- Rulings needed before CL planning: does a shopping "bought" tick add stock; may the bot confirm
  all matched lines unseen; is CL4's canonical catalog shared defaults or a household backup.
- `lib/i18n/{en,fi}.ts` are single shared dictionaries: one frontend lane per round owns them.
- The container has no Docker; PostgreSQL 16 and Redis are apt-installed and may vanish on reboot.
- Still operator-held: DEC-7 (camera scanning), DEC-8, DEC-9, meal sections, AG0; the Finnish
  wording pass; `LLM_MAX_TOKENS` 16384; an icon bundle (the repo library is still empty).

## Next action
Deploy d6ec2a7 and try the share target on Android; answer the three rulings; then `/plan-round`
from the CL items in `docs/TODO.md`.
