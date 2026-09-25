# Handoff
Generated-UTC: 2026-09-25T16:29:58Z
Base-SHA: f12b45649c2f239836ee4764266bf729b58ab9c3

## Round delta

Merged since the last handoff: the SQLAlchemy `<2.1` cap (#91, which turned `main`'s CI green
again), then H57 + H58 (#89, which also carries #90).

This round is **wave V, the fridge view**. It is three PRs, all based on `main`. Each contains
the one before it, so merge them in order:
- **#92** (`feat/v1-v3-fridge-view`): staleness tiers, `IngredientTile`, `FridgeView` on `/`,
  and the area grid route `/area/[id]`. A tile tap uses the item up.
- **#93** (`feat/v2-presence-not-amounts`): amounts leave the UI (item sheet, edit sheet, quick
  add, Gone, Undo label, receipt review). Backend and types unchanged.
- **PR 3** (`feat/v4-recently-used`): `GET /inventory?consumed_since=`; the area grid keeps
  used-up tiles grey for 24 h, and a tap brings them back (`useUnconsumeInventoryItem`).

Verified on PR 3's branch (which contains all three):
- frontend: 654 passed, tsc and lint clean, `next build` ok;
- backend: 1096 passed, ruff, format and mypy baseline clean;
- CI green on #92 and #93.

Still waiting on the model server (`192.168.0.247:9003` refuses connections from this
container): H54, and the H53 live selection test.

## Active PRs and conflicts

#92, then #93, then PR 3, merged in that order. Each later branch contains the earlier commits,
so nothing conflicts when they go in in order. Do not stage `.claude/README.md` or
`.claude/templates/profiles/python-fastapi.md`: they were modified before these sessions and are
unrelated.

## Non-obvious decisions or blockers

- **Run the live selection test on the homelab:**
  `pytest tests/services/test_live_selection.py -m requires_vllm -v`. The null cases are what
  the prompt change is for. If they still pick, the next lever is a JSON schema on the selection
  request (spec §3.3 asks for one; `select_products` sends none).
- **Operator, after deploying:** move "Ready meal: fish soup" to Ready Meals in the product
  editor. Also H56: *Estimate the guesses* on the products page.
- Stock already in the freezer is not re-dated when a product's frozen life changes (open box
  under "H52 as built").
- `tests/services/test_storage.py` cannot be collected on its own because of an import cycle
  (storage → schemas → category → storage). The full suite passes. Noted under "H55 as built".
- **Sandbox quirks in this container:**
  - Binaries under `node_modules/.bin` and `backend/.venv/bin` are not executable, so call them
    through `node …/jest.js`, `node …/tsc`, `node …/next` and `.venv/bin/python -m …`.
  - `frontend/.next` is not writable, so build from a scratchpad copy.
  - Several files are CRLF: edit them with an ending-preserving helper and check
    `git diff --stat` before committing.
- DB env for tests and alembic: `POSTGRES_SERVER=localhost POSTGRES_USER=kyokki
  POSTGRES_PASSWORD=kyokki POSTGRES_DB=kyokki REDIS_HOST=localhost KYOKKI_TEST_REQUIRE_DB=1`.

## Next action

Merge #92, #93 and PR 3 in order, then deploy and look at the fridge on the iPad. It has not
been seen in a browser: there is none in this container. After deploying: the operator runs
H56 (*Estimate the guesses*) and moves the fish soup to Ready Meals. Next: H54 and the H53 live
test in a session that can reach the model server, or wave H2 leftovers / H32 (a lock file,
which the SQLAlchemy 2.1 break argues for).
