# Handoff
Generated-UTC: 2026-09-19T09:00:00Z
Base-SHA: 8375d8f0e0d197a08b9440a2b95068eebd36e2b7

## Round delta

Thirteen increments merged (#52-#64): the whole of hardening wave **H0** and wave **H1**.

**H0 (#52-#56) - the gate in front of the acceptance week.**
- #52 H01/H02 - the test suite stopped wiping the dev database. It runs against
  `<POSTGRES_DB>_test`, creates it if missing, and refuses to start if the name does not end in
  `_test`. `Settings` is `extra="ignore"`, so the repo-root `.env`'s legacy keys no longer abort
  every local backend process while printing their values. `typecheck` compares against
  `backend/mypy-baseline.txt`.
- #53 H05 - no 500 on a reachable route. Deletes answer 409 naming what references the row, and
  the Open Food Facts mapper stopped returning three category ids that were never seeded.
- #54 H04/H06 - error boundaries, unknown vocabulary values render as themselves, and the flaky
  frontend run is fixed at the source.
- #55 H07/H08 - a receipt can always be finished: the enqueue race, re-reading a zero-line read,
  an image-only PDF reaching OCR, the stored extension, an upload cap, and Dismiss.
- #56 H03 - the runbook deploys what it says it does, and `/api/health` can actually fail.

**H1 (#57-#64) - identity is a key, not a score.** `docs/PRODUCT_RESOLUTION_SPEC.md` implemented
in full. Fuzzy similarity scored "Sour cream" 90 against "Cream" and confirm turned each such
guess into permanent verified memory. Now a line resolves through a learned alias or a known
catalog name; what is left gets a `pg_trgm` shortlist and one constrained model call per receipt,
and an answer is rejected unless it was on that line's shortlist. Nothing falls back to
similarity, and if the gateway is down the lines simply stay unresolved.

## Three things that were true and are not any more

Every hazard this file carried since 2026-09-17 is closed. Named here because the old wording is
quoted in `docs/reviews/` and in the per-area TODOs, and will mislead anyone who reads those
first:

- `test-backend` with the compose stack up is **safe** (H01).
- `docs/DEPLOY.md`'s own commands **work**, Telegram steps included (H03).
- A wrong pre-match is **no longer permanent** (H13-H15). It is labelled `auto` on the review
  row and one tap changes it; only the cook's own act writes verified memory.

## Active PRs and conflicts

None open.

## State of the deployment

Redeployed 2026-09-19 and verified from the workstation at `192.168.0.136`:

| check | result |
| --- | --- |
| `/api/health/live` (what the container healthcheck polls) | `{"status":"ok"}` |
| `/api/health` direct, port 17300 | `{"status":"ok","postgres":"ok","redis":"ok"}` in 0.11 s |
| `/api/health` through the frontend proxy, port 17301 | same |
| frontend root | 200 |
| data | 12 categories, 42 products, 3 confirmed receipts, **0 inventory items** |

That redeploy was built from `11897e0` (#63), so it has everything **except H18**. #64 merged
afterwards; `images.yml` rebuilds on push to main, and one more Portainer pull picks the product
editor up.

**H1's resolution has never run on the homelab.** All three receipts there were read by the old
matcher and are `confirmed`, which is terminal - `/process` refuses them, correctly. Proving the
new path needs a new receipt.

## Non-obvious decisions or blockers

- **Check `extraction_method` before trusting any extraction result.** `heuristic` means the
  model never ran: no categories, no generic names, no product estimates - and the receipt still
  reports `completed`. The gateway was reachable on 2026-09-18 (`c2.muse-glimmer` answered a
  selection call in 8.8 s); MinerU's `/api/v1/health` answered 404, which was not chased because
  H13 did not need it.
- **The extraction prompt still carries the catalog, on purpose.** H17 measured dropping it
  twice on the 49-line fixture: all 49 lines and generic names survive, but categories fall from
  40 to 30-31 and extraction is not faster. `EXTRACTION_OFFERS_CATALOG` turns it off. The numbers,
  and a finding worth revisiting - without the catalog the model picks *more specific* names,
  which may be the better answer - are in `docs/vLLM_MANUAL_TEST.md`.
- **CI tests the PR merged into main, not your branch.** Two PRs this round passed locally and
  failed in CI because a parallel PR had added a constraint in the meantime. When a wave adds
  migrations, rebase before trusting a green local run.
- The mypy baseline is **148**. A new model adds one unavoidable `Class cannot subclass "Base"`
  that every existing model already carries; `--update` it with a reason when that happens.
- Three migrations landed in H1, one of them irreversible (the `product_master` dedupe). All were
  rehearsed against seeded duplicate data on a scratch database before merging.

## Next action

**Read one real receipt.** Share it to the Telegram bot or upload it from the iPad. Nothing else
in the plan is blocked; this is the first exercise of H1 on real data, and what to look at is:

1. `extraction_method` - if `heuristic`, stop and check the gateway; nothing below means anything.
2. **Category count.** The baseline is **40 of 49** on a full S-market receipt.
3. **The chips on the review rows.** `known` means a key resolved it, `auto` means the model
   proposed it from a shortlist. On an early receipt against a 42-product catalog, expect mostly
   `auto` and some unresolved - that is correct, not a failure. The catalog learns as you confirm.
4. Anything `auto` that looks wrong: tap **Change**. That is now a correction rather than a
   permanent mistake.

Then **MVP-P3, the acceptance week** (`docs/TODO.md`): five real Finnish receipts end to end from
the iPad, each under two minutes, with a friction log.

After P3: waves **H2-H4** (`docs/TODO.md`), which need operator answers to **DEC-5 to DEC-9**
first, then the agent interface track (`docs/agent_TODO.md`).
