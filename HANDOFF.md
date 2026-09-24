# Handoff
Generated-UTC: 2026-09-24T19:56:37Z
Base-SHA: e60b95af689cdbeb0294b113287acfbb56c5c14c

## Round delta

Merged since the last handoff: H52 (#86, re-configurable product, migration `c2d9e4a17b35`) and
H55 (#87, `ready_meals` category).

On `feat/h53-shortlist` (cut from the SHA above): **H53, a shortlist that contains the answer**
(Q14). Backend only, no migration.

- `TrigramRetriever` ranks the whole catalog on one score, in this order:
  1. a shared whole word;
  2. `similarity` or `word_similarity`, whichever is higher, checked in both directions;
  3. the line's category, as a tiebreak.

  It replaces the alphabetical category fill, and products with no name row are included.
- The selection prompt now says a shared word does not mean the same product and that null is a
  good answer, with a worked example (not the reported pairs).
- `tests/fixtures/resolution/reported_pairs.json` covers the four reported pairs. The retriever
  tests are deterministic. `tests/services/test_live_selection.py` is marked `requires_vllm`.

Verified:
- Backend: 1082 passed, 1 skipped. ruff clean, mypy baseline none new, vocabularies agree.
- The melon case, the category ranking and the canonical-name fallback failed on the old
  retriever. The prompt tests failed on the old prompt.
- **The live selection test has not run:** the gateway `192.168.0.247:9003` refuses connections
  from this container.

## Active PRs and conflicts

The H53 PR (this branch). Do not stage `.claude/README.md` or
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

Merge the H53 PR. Next is **H54** (a Finnish glossary in the extraction prompt). Its merge gate
is a before/after run on the 49-line fixture, which needs the gateway. Plan it for a session that
can reach the homelab, or have the operator run the measurement. H57 (seed shelf lives) and H58
(shelf-life audit view) need no gateway. Wave V (V1-V4) is planned and not started.
