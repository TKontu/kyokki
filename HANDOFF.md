# Handoff
Generated-UTC: 2026-09-25T18:54:54Z
Base-SHA: 5503508243cccd1b9092470108f288b524a0da6a

## Round delta

- Merged: #91 (SQLAlchemy capped `<2.1`), #89 (H57 placeholders + H58 audit view, via #90), and
  wave V, the fridge view: #92 (tiles, fridge `/`, area grid `/area/[id]`), #93 (amounts out of
  the UI), #94 (grey used-up tiles for 24 h, tap to bring back; `GET /inventory?consumed_since=`).
- Uncommitted on `docs/after-wave-v`: `docs/TODO.md` and `docs/frontend_TODO.md` mark wave V
  done, with an open "look at it on the iPad" box.

## Active PRs and conflicts

None open. Do not stage `.claude/README.md` or `.claude/templates/profiles/python-fastapi.md`:
they are unrelated edits that predate these sessions.

## Non-obvious decisions or blockers

- **Wave V has never been seen in a browser or on the iPad.** The tests assert no numbers on
  screen and every tap, not the layout.
- **Un-consume is a PATCH** of `current_quantity = initial_quantity` (a logged, undoable
  correction). `restore` leaves an empty item empty.
- **The backend still stores amounts.** The UI hides them (operator ruling 2026-09-24). Quick
  add sends the product's usual amount, else 1. A receipt line read as 0 goes in as 1.
- **Blocked on the model server**, which is unreachable from this container: H54 (its merge gate
  is a fixture run) and the H53 live test, `tests/services/test_live_selection.py -m requires_vllm`.
- **Operator, after deploying:** run H56 (*Estimate the guesses*) and move the fish soup to
  Ready Meals.
- **The SQLAlchemy cap is a stopgap.** H32 (a lock file) is the fix. 2.1 needs psycopg 3 or an
  explicit driver, and brings new mypy errors.
- **Container quirks:**
  - `.venv/bin/*` and `node_modules/.bin/*` are not executable, so run them through
    `python -m …` or `node …`;
  - `frontend/.next` is not writable, so build from a scratchpad copy;
  - many files are CRLF, so preserve endings;
  - pipe git output (`--no-pager`), because a pager hung the shell.

## Next action

Commit the two TODO edits on `docs/after-wave-v` and open a docs PR. Then the operator deploys
and reviews the fridge on the iPad, logging friction under a new log in `docs/TODO.md`.
