# Handoff
Generated-UTC: 2026-09-26T06:00:00Z
Base-SHA: e71acffb85c3b7e113460c00565f750df2fd0c73

## Round delta

- **Round 2026-09-25-3 is merged** (merge commits d2ef3ae, af63d6b, e71acff) and deployed on
  2026-09-26:
  - #97 AG1 agent tokens, with reviewer fixes;
  - #99 H54 Finnish glossary and the H53 live run (measured with the catalog on);
  - #98 AG2 agent stock and product endpoints (retry-safe add).
- **The operator's first look at the fridge on the iPad** produced friction Q17-Q19
  (`docs/TODO.md`):
  - the fridge doesn't look like a fridge;
  - every item shows its category emoji;
  - everything shows as going stale.
- **Round 2026-09-26-6 is planned**, six lanes, from `e71acff`:
  - A1: Q19 kitchen shelf lives;
  - A2: Q17 fridge mocks;
  - A3: Q18 icon spike;
  - A4: AG3 CLI;
  - A5: AG6 low-stock shopping;
  - A6: the WebSocket token log redaction.

  Specs and prompts are in `.rounds/2026-09-26-6/`, which is gitignored and local to the
  planner's workstation.

## Active PRs and conflicts

- The docs PR for this round: `docs/round-2026-09-26-6`.
- Lanes A1-A6 each open one PR.
- Their owned paths are disjoint. The alembic head belongs to A1 alone.
- Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`. They are
  unrelated edits that predate these sessions.

## Non-obvious decisions or blockers

- **Operator rulings for Q19 (2026-09-26):**
  - red only in the last 1-2 days;
  - reference shelf lives: tomato and orange well over 5 days, banana 5, packed meat 5,
    meat from the butcher's counter 3, fish 3;
  - the estimator is the shelf-life authority for new products.
- **After Q19 deploys,** the operator runs "Re-estimate all (keeps yours)" on the products
  page: a dry run, then apply. This supersedes H56.
- **Gateway slots:**
  - `c2.muse-glimmer` is production and A1's measurement slot;
  - `c2.qwen3.8-27b` is for A3's spike;
  - `c0.*` is the operator's agent, never used here.
- **DB tests run locally now.** PostgreSQL 16 binaries are in `/usr/lib/postgresql/16/bin`.
  Run a private cluster per lane (`POSTGRES_SERVER=127.0.0.1:<port>`) with
  `KYOKKI_TEST_REQUIRE_DB=1`.
- **Project settings deny `gh pr merge`** (`.claude/settings.json`). The operator runs the
  merges (`!gh pr merge <n> --merge`).
- **Container quirks:**
  - `.venv/bin/*` and `node_modules/.bin/*` are not executable;
  - `frontend/.next` is not writable;
  - many files are CRLF;
  - pipe git through `--no-pager`.

## Next action

Merge the docs PR. Dispatch A1-A6 (one executor per `.rounds/2026-09-26-6/prompts/A<n>.md`,
with the preamble). Then run `/review-round` and `/merge-round`. After deploy, the operator
re-estimates the catalog and picks a fridge mock and an icon route.
