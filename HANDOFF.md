# Handoff
Generated-UTC: 2026-09-25T09:30:00Z
Base-SHA: 31dd9012eb78a535a1a873c10f01182283fadb05

## Round delta

Merged since the last handoff: H53 (#88, a ranked shortlist and a null example in the selection
prompt).

This round is two PRs, both cut from the SHA above:
- **H57** (`feat/h57-placeholders`): new category placeholders, chosen by the operator on
  2026-09-25 (produce 7, dairy 10, beverages 180, snacks 90). Data migration `e8b4f1c62a90`
  moves only the rows that still hold the old seed value. Backend 1090 passed; ruff, mypy
  baseline, `alembic check` and the upgrade/downgrade round trip are clean.
- **H58** (`feat/h58-shelf-life-audit`): the shelf-life audit view on the products page.
  Frontend only.

H54 is still waiting: its merge gate is a before/after run on the model server, and
`192.168.0.247:9003` refuses connections from this container. The H53 live selection test is
also still unrun, for the same reason.

## Active PRs and conflicts

The H57 and H58 PRs. They touch different files except `docs/TODO.md`, and there each edits
its own row and its own as-built block. Do not stage `.claude/README.md` or
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

Merge H57 and H58. Next: **H54** (the Finnish glossary), in a session that can reach the model
server, together with the H53 live selection test. After deploying: the operator runs H56
(*Estimate the guesses*) and moves the fish soup to Ready Meals. Wave V (V1-V4) is planned and
not started.
