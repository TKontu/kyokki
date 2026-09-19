# Handoff
Generated-UTC: 2026-09-19T10:45:30Z
Base-SHA: ae9275b31a023c51534e7f5b13827620aea6bd79

## Round delta

Four increments merged (#65-#68), all from the **acceptance-week friction log**: the first real
receipt through the rebuilt pipeline, read on the iPad on 2026-09-19. Recorded as **Q7-Q10** in
`docs/TODO.md`, continuing Q1-Q6.

- **#66 Q7 - the catalog block was silencing the estimates.** Meat came back with `sl: null` on
  every line, so mince, ham and salami all fell back to the `meat` category's 5 days. The plan
  blamed missing meat examples in the prompt. The measurement disproved it: with an empty catalog
  the model estimates meat fine. The cause was the known-products clause - *"set pw, sl and os to
  null for it, the system already knows those"* - which the model applied to the **whole receipt**.
  Removing it is better on both axes: shelf lives 4-12 of 49 back to 37-39, and ~20 % faster.
- **#67 Q8 - a pack has a weight.** `product_master.pack_grams` (migration `d1a7f4b62e93`). One
  pack of mince now stores as 400 g, not `1 pcs`; the review row shows `1 pcs → 400 g`. A piece
  weight still wins, so `SIPULI 500G` stays counted. This is Q3's other direction: #48 made a
  known piece weight mean "counted", and nothing made a known pack weight mean "measured".
- **#68 Q9+Q10 - a bad read is visible, and a stale receipt says so.** Every receipt now says how
  it was read, on the list row, the review header and the confirmed screen. And the review footer
  warns when a receipt is over a fortnight old, because expiry is counted from the receipt's date.
- **#65** was the previous round's handoff, merged after it had gone stale; this file replaces it.

## The one finding worth carrying forward

**muse-glimmer's per-line estimates are fragile to prompt complexity, and it fails silently.**
Twice in one round a prompt change quietly destroyed estimates it was not aimed at:

| what changed | intended effect | actual collateral |
| --- | --- | --- |
| the known-products clause (pre-Q7) | skip re-deriving what the catalog holds | shelf lives 39 -> **4-12** of 49, receipt-wide |
| a `pk` contract field (Q8) | ask for the pack weight | answered **1 of 49**, and shelf lives 39 -> 26 -> **4** |

Both looked reasonable. Neither announced itself: the response still parsed, the receipt still
reported `completed`, and only a count of non-null estimates showed the damage. `pk` was reverted
and pack weight now comes from a printed `500G`, the catalog, or the cook.

**So: measure a prompt or contract change on the 49-line fixture before keeping it, count the
other estimates and not just the new field's, and run it twice** - H17 saw a 12 s swing between
identical runs. Numbers and harness shape in `docs/vLLM_MANUAL_TEST.md`.

## Active PRs and conflicts

None open.

## State of the deployment

Unchanged since the 2026-09-19 redeploy verification in the previous handoff: healthy on all
checks, 12 categories, 42 products, 3 confirmed receipts. That build predates **#64 and
everything in this round**, so a Portainer pull is needed to pick up the product editor (H18),
Q7's prompt fix, Q8's pack weights and Q9/Q10's read visibility.

**Migration `d1a7f4b62e93` has not run on the homelab.** It adds one nullable column to
`product_master`, was rehearsed up, down and up again on a scratch database, and needs no
backfill - NULL already means what every existing product means.

## Non-obvious decisions or blockers

- **Check `extraction_method` before trusting any extraction result.** This is now visible
  everywhere instead of only on the review screen (Q9), so it is one glance from the receipts
  list. `read without the model` means no categories, no generic names, no estimates.
- **Expiry is counted from the receipt's date, not the day of adding**, and that is deliberate.
  The operator's June receipt adding items three months expired was correct, and the date had
  been read correctly - confirmed 2026-09-19. Q10 warns; it does not change the arithmetic.
- **Q7 only helps new products.** `_fill_gaps` never overwrites a stored shelf life (Q2's "do not
  undo a correction every week"), so `Ground beef`, `Ham`, `Sausage` and `Chicken fillet` already
  at 5 days on the homelab need the product editor. **Whether a later, better estimate should
  correct a stored one is open** - `Rye crispbread` sits at 5 days while the model said 720.
- **CI does not re-check a PR title that was edited**... it does now (#67). The workflow listened
  only for `opened/synchronize/reopened`, and re-running the job replays the stale payload, so a
  retitle could not fix a failing title check without an unrelated commit. `edited` was added.
  **Titles take no scope:** `feat:`, not `feat(products):`.
- **CI tests the PR merged into main, not your branch.** #68 branched before #67 and the two
  touched the same test fixture; the merge happened to be clean, verified on `ae9275b` after the
  fact (854 backend, 556 frontend, tsc clean). It could as easily not have been.
- The mypy baseline is **148**, unchanged this round.

## Next action

**Redeploy, then read a second real receipt.** The first one produced this whole round, and every
fix in it is unproven on real data:

1. Portainer pull (the running build predates #64), then
   `docker compose -f docker-compose.prod.yml run --rm kyokki-api alembic upgrade head`.
2. Share a receipt with meat on it. Look for: `read by the model` on the receipts list; a
   **shelf life that differs per meat** rather than a uniform 5 days; `SIKA-NAUTAJAUHELIHA`
   arriving as **grams** if the catalog has learned its pack weight, or as `1 pcs` with one
   correction available in the product editor if it has not.
3. The stale-receipt warning should **not** appear on a receipt from this week.

Then **MVP-P3, the acceptance week** (`docs/TODO.md`): five real Finnish receipts end to end from
the iPad, each under two minutes, with a friction log. Two of the five are now done and they
produced Q7-Q10, which is the process working.

After P3: waves **H2-H4**, which need operator answers to **DEC-5 to DEC-9** first, then the
agent interface track (`docs/agent_TODO.md`).
