# Handoff
Generated-UTC: 2026-09-24T17:33:54Z
Base-SHA: 52b317a34c823bfa7e25f7f1d4bdbdd63369c25b

## Round delta

Uncommitted on `feat/h51-model-guess-is-not-a-key` (cut from the SHA above): **H51, a model
guess never becomes a key** (Q13). Backend only, no migration, no frontend change.

- `known_names` returns `KnownName(product, source)`; tier 4 resolves a `product_name` row
  the model taught as `("name", verified=False)`, so the review row shows "auto".
- Confirm learns the generic name as the cook's only when the cook changed the product or
  typed the name; keeping an alias, a name hit or a selection learns it as `model`.
- `learn_product_name` re-points a `model` row to a `cook` or `canonical` claim, upgrades a
  product's own `model` row to `cook` in place (returns False; merge counts on it).
- `product_for_name(trust_model=False)` when confirm gets a name with no product id, so
  "New product: Ketchup" creates Ketchup instead of resolving to a model's guess.
- Also uncommitted from the same session: wave H5 (H51-H58) and the 2026-09-24 friction log
  in `docs/TODO.md`, the H5 row in `docs/backend_TODO.md`, spec §3.2/3.4/3.5 wording.

Verified: 1028 passed, 1 skipped (external-service markers excluded); ruff and mypy baseline
clean; the 20 new tests fail on the stashed old code.

## Active PRs and conflicts

None open. Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`:
modified before this session, unrelated to H51.

## Non-obvious decisions or blockers

- **Operator rulings 2026-09-24:** a kept selection is *learned* (as `model`), not silenced;
  the product stays re-configurable by the cook (category, shelf life, frozen life, matching
  names) - that is H52 as widened; frozen life is per product with the category as fallback.
- **This container had no Postgres.** Installed with apt this session (`sudo service
  postgresql start`, `redis-server start`; role/db `kyokki`/`kyokki`, `CREATEDB` so the suite
  can make `kyokki_test`). Run tests with the env in the previous handoff and
  `backend/.venv/bin/python -m pytest` by absolute path; a relative `.venv/bin/python` failed
  after `cd` once.
- `pytest -m "not requires_db"` overrides the ini's marker exclusions, so add the three
  `requires_*` markers back or the connection tests fail on network alone.
- 54 of 65 homelab products still carry the category placeholder (H56 is an operator action).

## Next action

Commit and open the PR for this branch (template in `CLAUDE.md`; `/commit-push-pr`), then
start **H52** from its row in `docs/TODO.md` (wave H5): category picker,
`frozen_shelf_life_days` per product + migration, `GET/DELETE /products/{id}/names`.
