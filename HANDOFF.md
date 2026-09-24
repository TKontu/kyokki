# Handoff
Generated-UTC: 2026-09-24T18:35:09Z
Base-SHA: d72a3f7ec83568ea19854160b57a06f9578ae6c7

## Round delta

Since the last handoff: H51 merged as PR #85 (with the wave V plan as a docs commit).

Uncommitted on `feat/h52-product-is-reconfigurable` (cut from the SHA above): **H52, the
product is re-configurable**. Backend, frontend, one migration (`c2d9e4a17b35`, head).

- Product editor: category picker; frozen life per product (blank = the category's); a
  "Matching names" list with "yours" / "auto" chips and a two-tap remove.
- `product_master.frozen_shelf_life_days` (nullable); `_start_frozen_clock` prefers it.
- A category change carries `storage_type` and, for a `category` placeholder, the new
  category's shelf life, re-dating `calculated` stock.
- `GET /products/{id}/names`, `DELETE …/names/{name_id}` (409 canonical),
  `DELETE …/aliases/{alias_id}`; new `crud/store_product_alias.py`, `schemas/product_names.py`.
- A rename now keeps `product_name` true (old canonical row → `cook`, new name canonical).
  This was a latent bug found while building H52.
- `broadcast_product_update` (new `product_update` message; nothing listens yet).
- `NameSource` added to `scripts/check_vocabularies.py`.

Verified:
- Backend: 1056 passed, 1 skipped. ruff clean, mypy baseline none new, vocabularies agree.
- Migration: `alembic upgrade`/`downgrade`/`upgrade` and `alembic check` clean on the local database.
- Frontend: 693 passed, tsc and lint clean, `next build` ok.
- The new tests failed before the implementation.

## Active PRs and conflicts

None open. Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`:
modified before these sessions, unrelated.

## Non-obvious decisions or blockers

- **Stock already in the freezer is not re-dated** when a product's frozen life changes;
  nothing records when it went in. Open checkbox under "H52 as built" in `docs/TODO.md`.
- A cook-typed or model-estimated shelf life does not follow a category change; only the
  `category` placeholder does.
- **Sandbox quirks in this container:** binaries under `node_modules/.bin` and
  `backend/.venv/bin` are not executable, so call them through the interpreter:
  - `node node_modules/jest/bin/jest.js`
  - `node node_modules/typescript/bin/tsc --noEmit`
  - `node node_modules/next/dist/bin/next lint`
  - `.venv/bin/python -m alembic`

  Writes to `frontend/.next` are refused, so run `next build` from a copy in the scratchpad
  with `node_modules` symlinked.
- DB env for tests and alembic: `POSTGRES_SERVER=localhost POSTGRES_USER=kyokki
  POSTGRES_PASSWORD=kyokki POSTGRES_DB=kyokki REDIS_HOST=localhost KYOKKI_TEST_REQUIRE_DB=1`.
- `pytest -m "not requires_db"` overrides the ini's marker exclusions, so add the three
  `requires_*` markers back or the connection tests fail on network alone.
- 54 of 65 homelab products still carry the category placeholder (H56 is an operator action).
  After deploying H52, the migrate job applies `c2d9e4a17b35`.

## Next action

Commit and open the PR for this branch (`/commit-push-pr`). Then the H5 order continues:
**H55** (`ready_meals` category), H53, H54, H57, H58. Wave V (the fridge view, V1-V4) is
planned and not started; its order relative to the rest of H5 is the operator's call.
