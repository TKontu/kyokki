# Handoff
Generated-UTC: 2026-09-20T10:09:21Z
Base-SHA: a7aee4807a6d0ccefe3099e824351ee6d6548da0

## Round delta

Thirteen increments merged (#65-#78): the **acceptance-week friction log** finished, then the
first two items of hardening wave **H2** taken early.

**The stock screen (#77, #78).** Two findings from the daily-loop audit, one of them H23's own
debt: freezing `discarded` removed the only way back from a mis-tapped *Mark as gone*, so the
toast carries **Undo** now - and the 2026-09-13 "No Undo" ruling is revisited rather than ignored,
because H23 built the clean reversal it said did not exist. Consume still has none. Separately,
expired items had pinned themselves to the top of the list forever with no lower bound on
"expiring soon"; they have their own red section, a real age instead of the bare word `Expired`,
and a clear that records them as **thrown away** in one transaction.

**H2, started out of order (#75, #76).** The operator's call, for two reasons: H23 is silent
data loss in the most-used action, and H23 and H24 are two of the three agent-track hard
prerequisites that need no decision first.
- **#75 H23 - one status machine.** `consume_inventory_item` was read-modify-write with no lock,
  so two taps both read 4, both passed the check and both wrote 3 - one helping gone, both log
  rows written. Both writers lock now, and the rules became a table, which turned up three more:
  discard did not freeze the item, a correction above full kept a stale label, and create
  enforced nothing. `contracts/status-transitions.json` is the single copy of the rule, read by
  both test suites, because the iPad predicts the status too.
- **#76 H24 - closed vocabularies.** The create path took any string where PATCH answered 422 for
  the same value. Eight `StrEnum`s now, following `ReceiptStatus`; four spellings of "location"
  became one; and `scripts.check_vocabularies` runs in CI, because `frontend/types/` mirrors the
  schemas by hand and four fields crossed in one month only by accident.

The friction log itself (#65-#74): the first real
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
- **#70 + #71 Q11 - the catalog can change its mind.** Q7's fix was inert on the catalog it was
  written for: 46 of 50 products carried their category's blanket figure and nothing could revise
  one, because `_fill_gaps` had no shelf-life branch and the NOT NULL column could not tell a
  placeholder from an answer. `shelf_life_source` separates them; `POST /products/estimate` asks
  the model about the catalog's own names (46 of 46, 52-57 s, mince 5 -> 2 days); and `/products`
  is the first screen from which a product not in stock can be corrected at all.
- **#73 + #74 Q12 - expiry keeps up.** Q11 changed the catalog's mind but not the food:
  `build_inventory_item` dates an item once, at confirm, so correcting mince to two days left the
  mince in the fridge still claiming five. A correction now re-dates the stock it dated - skipping
  anything you typed yourself, anything already gone, and capping opened items so a longer shelf
  life cannot undo Q5's shortening. **DEC-10 settled with it:** moving something to the freezer
  re-dates it from a per-category frozen figure and marks it `frozen`, which is what stops the
  recompute thawing that clock again.
- **#72** existed only to fix my own mistake: #71 was opened with `--base` on #70's branch, GitHub
  did not retarget it in time, and it merged into a dead branch instead of `main`. **Do not stack
  PRs that way here** - target `main` and say "merge after #N" in the body.
- **#65** was the previous round's handoff, merged after it had gone stale; this file replaces it.

**Still open and worth knowing:** nothing lists inactive items, so *"Put it back"* in the edit
sheet is reachable only through the Undo window on the toast. A screen for them forces a question
the app has no answer to - how long should something stay visible after you bin it - and the
operator set it aside deliberately.

**And nothing reads the waste log back.** Every discard writes a `consumption_log` row and always
has; there is no router for it. The clear is being scrupulous about recording waste that no-one
can yet see. That is **H46**.

## The one finding worth carrying forward

**muse-glimmer's per-line estimates are fragile to prompt complexity, and it fails silently** -
and separately, **the same call can have an off day.** Twice in one round a prompt change quietly
destroyed estimates it was not aimed at:

| what changed | intended effect | actual collateral |
| --- | --- | --- |
| the known-products clause (pre-Q7) | skip re-deriving what the catalog holds | shelf lives 39 -> **4-12** of 49, receipt-wide |
| a `pk` contract field (Q8) | ask for the pack weight | answered **1 of 49**, and shelf lives 39 -> 26 -> **4** |

Both looked reasonable. Neither announced itself: the response still parsed, the receipt still
reported `completed`, and only a count of non-null estimates showed the damage. `pk` was reverted
and pack weight now comes from a printed `500G`, the catalog, or the cook.

And on 2026-09-19 the **unchanged** fixture, with `llm_extractor.py` byte-identical to `main`,
returned **18** shelf lives on one run and **39** on the next two. Nothing in the tree could
explain it, because nothing in the tree had changed.

**So: measure a prompt or contract change on the 49-line fixture before keeping it, count the
other estimates and not just the new field's, and run it twice.** A single run cannot tell a
regression from noise **in either direction** - a one-run 18 would have read as a regression, and
a one-run 39 would have hidden one. Numbers and harness shape in `docs/vLLM_MANUAL_TEST.md`.

## Active PRs and conflicts

None open.

## State of the deployment

Unchanged since the 2026-09-19 redeploy verification in the previous handoff: healthy on all
checks, 12 categories, 42 products, 3 confirmed receipts. That build predates **#64 and
everything in this round**, so a Portainer pull is needed to pick up the product editor (H18),
Q7's prompt fix, Q8's pack weights and Q9/Q10's read visibility.

**Three migrations have not run on the homelab**: `d1a7f4b62e93` (pack weight), `f2c91b45d8a7`
(shelf-life provenance) and `b7e3d5c19f02` (frozen shelf lives). The first two were rehearsed up,
down and up again on a scratch database; **`b7e3d5c19f02` was not** - local Docker is no longer
available on this workstation, so its only exercise is CI, which runs `alembic check` and the
whole suite against a real Postgres. It adds one nullable column and fills eight of the twelve
seeded categories.
`f2c91b45d8a7` backfills by comparing each product against its category, which is a heuristic in
one direction only: a model estimate that happens to equal its category's figure reads as a
placeholder and becomes overwritable. No correction is ever mislabelled.

## Non-obvious decisions or blockers

- **Check `extraction_method` before trusting any extraction result.** This is now visible
  everywhere instead of only on the review screen (Q9), so it is one glance from the receipts
  list. `read without the model` means no categories, no generic names, no estimates.
- **Expiry is counted from the receipt's date, not the day of adding**, and that is deliberate.
  The operator's June receipt adding items three months expired was correct, and the date had
  been read correctly - confirmed 2026-09-19. Q10 warns; it does not change the arithmetic.
- **Q7 only helped new products, and Q11 (#70, #71) is why that mattered.** Measured on the live
  catalog: 46 of 50 products carried their category's blanket figure. `_fill_gaps` had no
  shelf-life branch at all, so a later estimate was dropped rather than refused. Now
  `shelf_life_source` separates a placeholder from an answer, `POST /products/estimate` repairs
  the placeholders (46 of 46 answered, 52-57 s), and `/products` can reach every product rather
  than only the ones in stock. **Still open, and narrower:** whether a model estimate should
  replace an earlier model estimate. No named product needs it.
- **Correcting a product now moves the stock it dated (Q12, #73)** - but only stock whose date
  the system worked out. Anything you typed is `manual`, anything frozen is `frozen`, and neither
  is touched. The 13 expired items from the June receipt still do not heal and should not: they
  were dated from a June purchase, so the recompute gives the same answer. That food really is
  three months old.
- **Consume and correction are locked now (#75).** The lock lives inside the CRUD functions,
  not the endpoints, because consume has two callers - the API and the scanner. Picking the item
  in `scanner_service` is still unlocked and its cap is advisory; that surface is DEC-7's.
- **The status rules are a table** (`services/item_status.py`) and the iPad's copy answers to the
  same `contracts/status-transitions.json`. Changing one implementation without the other fails a
  test rather than flickering a wrong label on the wall display.
- **CI does not re-check a PR title that was edited**... it does now (#67). The workflow listened
  only for `opened/synchronize/reopened`, and re-running the job replays the stale payload, so a
  retitle could not fix a failing title check without an unrelated commit. `edited` was added.
  **Titles take no scope:** `feat:`, not `feat(products):`.
- **CI tests the PR merged into main, not your branch.** #68 branched before #67 and the two
  touched the same test fixture; the merge happened to be clean, verified on `ae9275b` after the
  fact (854 backend, 556 frontend, tsc clean). It could as easily not have been.
- The mypy baseline is **150**, and has come down three times in three rounds rather than up. It grew twice in Q11 (untyped legacy `Column[...]` assignments,
  reason written into the file) and came **down** by one in Q12, when folding the scanner's
  duplicate expiry formula into `sealed_expiry` deleted an error with it. Note `--update`
  regenerates the file and drops its comments; there is a line in it saying so.
- **No Docker on this workstation.** DB-backed tests, migration rehearsals and `alembic check`
  run in CI, not locally. What runs locally is `pytest -m "not requires_db and not
  requires_mineru and not requires_vllm and not requires_ollama"` (406 tests, and it still needs
  `POSTGRES_*`/`REDIS_HOST` set to *something* because `Settings` requires them), plus ruff,
  the mypy baseline, and the whole frontend suite.

## Next action

**Redeploy, then read a second real receipt.** The first one produced this whole round, and every
fix in it is unproven on real data:

1. Portainer pull (the running build predates #64): the stack → **Pull and redeploy**, with
   *re-pull image* ticked. **That is the whole of it.** `kyokki-migrate` runs `alembic upgrade
   head` and seeds the categories before the other services start
   (`docker-compose.prod.yml:55-61`), so the separate `alembic upgrade head` this file used to
   tell you to run was never needed - that instruction was wrong and is now gone.
2. **Open `/products` and run "Estimate the guesses".** It proposes and writes nothing until a
   second tap. Expect the six meat products to stop reading 5 days apiece, and `Rye crispbread`
   to become 720. This is the one step that repairs the catalog the first four receipts built.
3. Share a receipt with meat on it. Look for: `read by the model` on the receipts list; a
   **shelf life that differs per meat** rather than a uniform 5 days; `SIKA-NAUTAJAUHELIHA`
   arriving as **grams** if the catalog has learned its pack weight, or as `1 pcs` with one
   correction available in the product editor if it has not.
4. The stale-receipt warning should **not** appear on a receipt from this week.
5. Put something in the freezer from an item's edit sheet. Its date should jump to the frozen
   figure for its category and **stay there** through the next estimate (Q12, DEC-10).

Then **MVP-P3, the acceptance week** (`docs/TODO.md`): five real Finnish receipts end to end from
the iPad, each under two minutes, with a friction log. Two of the five are now done and they
produced Q7-Q10, which is the process working.

After P3: waves **H2-H4**, which need operator answers to **DEC-5 to DEC-9** first, then the
agent interface track (`docs/agent_TODO.md`).
