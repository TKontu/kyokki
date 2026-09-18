# Handoff
Generated-UTC: 2026-09-17T17:17:34Z
Base-SHA: e233db5069bacd9e29f7b45cb3cc927e3f71d69b

## Round delta
Four increments merged (#47-#50). The operator friction log Q1-Q6 is now closed:

- #47 MVP-P2 - manifest, icons, always-on refresh, dark mode following the device.
- #48 Q2/Q3/Q6 - `product_master` carries `avg_piece_grams`; `default_unit` and
  `default_shelf_life_days` stop being frozen copies of the category's. Weighed produce is
  stored in pieces.
- #49 Q4/Q5 - consume options derived from the item; opening a pack shortens its expiry.
- #50 Q1 - `household` is a sentinel in the `c` enum rather than a discarded answer, plus a
  `non_food_name` memory; the review screen folds those lines into the footer.

#49 also fixed a live bug: categories were compared case-sensitively, so the model answering
"Dairy" for the id `dairy` nulled all 49 and confirm could create nothing.

## Active PRs and conflicts
None open.

## Non-obvious decisions or blockers
- **The LLM gateway and MinerU were both unreachable when the session ended.** Receipts then
  fall through to the heuristic parser, which produces no categories, no generic names and no
  product estimates - and still reports `completed`. Check `extraction_method` before trusting
  any extraction result; `heuristic` means the model never ran.
- Q1's `household` sentinel is **unit-tested only** - the gateway died before a live run could
  confirm the model actually answers it. The memory half is proven on the real fixture. Check
  the category count on the first real receipt: the baseline is 40 of 49, and this contract has
  moved it before.
- The mypy baseline is **149**, not 148. A new model adds one unavoidable
  `Class cannot subclass "Base"` that every existing model already carries.
- The deployment is six increments behind and still runs the pre-#49 category bug, so receipts
  scanned there right now produce rows confirm cannot turn into products.

## Reviews (2026-09-17, same session, uncommitted)
Five pipeline reviews under `docs/reviews/` covered every surface at `23b83ad`, and
`docs/PRODUCT_RESOLUTION_SPEC.md` replaces fuzzy matching. `docs/TODO.md` now carries a
hardening track (H0-H4, DEC-5 to DEC-10) between MVP-P3 and the post-MVP frontier; the
per-area TODOs point at it. Three things to know before doing anything else:
- ~~Do not run `test-backend` with the compose stack up~~ — **fixed in H01 (PR #52)**. The
  suite runs against `<POSTGRES_DB>_test`, creates it if missing, and refuses to start if the
  name does not end in `_test`. The dev database is out of reach.
- ~~Do not deploy the Telegram service from the runbook's own commands~~ — **fixed in H03**:
  every `docker compose` command in `docs/DEPLOY.md` now carries `--env-file stack.env`.
- **Fuzzy matching pre-selects wrong products** (Pineapple -> Apple at 90 "high") and confirm
  learns them as verified aliases. Until H13-H15 land, skip any pre-matched line that looks
  wrong rather than including it; a skip teaches nothing, an include is permanent.

## Next action
Redeploy the homelab, then read one real receipt and check the category count.
`docs/DEPLOY.md` section "Updating": Portainer -> **Pull and redeploy**, with *re-pull image*
ticked. Everything from #46 onward - `/scan`, `/receipts`, the nav rail, the PWA, piece
counting, the category fix - is built, green and unreleased.
Then wave H0 (H01-H08) before or alongside the acceptance week, and DEC-5 to DEC-9 need
operator answers before H2/H3 can be assigned.
