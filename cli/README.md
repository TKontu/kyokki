# kyokki CLI

A command-line client for the Kyokki API, built for agents (and people) on the LAN.
It talks HTTP only; it shares no code with the backend.

## Install

```bash
pipx install ./cli          # or: pip install ./cli
export KYOKKI_URL=http://kyokki.lan:17300
export KYOKKI_TOKEN=...     # an API token from KYOKKI_API_TOKENS on the server
kyokki doctor
```

`--url` and `--token` override the environment. The URL is the server's base (a trailing
`/api` is dropped, so `http://kyokki.lan:17300/api` works too); one that does not parse is
a usage error (exit 2). The token is only ever sent as the `Authorization: Bearer` header,
and the CLI never prints it, whatever its length. Surrounding whitespace is stripped (a
token read from a CRLF file works); a token that still holds a control or non-ASCII
character is refused with exit 2 before anything is sent, without repeating it.

## Commands

| Command | What it does |
| ------- | ------------ |
| `kyokki doctor` | Reachability, then which token you are and whether auth is on |
| `kyokki stock list [--q NAME] [--location L] [--expiring DAYS] [--category ID]` | Stock per product, soonest to expire first |
| `kyokki stock add NAME QUANTITY [UNIT] [--category ID] [--location L] [--expiry YYYY-MM-DD] [--purchased YYYY-MM-DD]` | Add stock; a new product needs `--category` |
| `kyokki stock consume NAME AMOUNT UNIT [--location L] [--allow-partial] [--dry-run]` | Use up stock, first to expire first |
| `kyokki product resolve NAME` | What a name means: a match, candidates, or a suggestion |
| `kyokki product name add PRODUCT_ID NAME` | Teach a product another name |
| `kyokki category list` | Category ids for `--category` |
| `kyokki shopping list [--all] [--priority P]` | Open shopping items, urgent first (`--all` adds the bought ones) |
| `kyokki shopping add NAME [AMOUNT UNIT] [--priority P] [--product-id UUID]` | Put an item on the list; a free-text item without AMOUNT UNIT is 1 pcs, `--product-id` needs AMOUNT UNIT |
| `kyokki shopping done ID [--undo]` | Tick an item off as bought, or put it back with `--undo` |
| `kyokki shopping remove ID` | Delete an item from the list |
| `kyokki shopping generate [--from low-stock] [--dry-run]` | Put what the kitchen is short of on the list |
| `kyokki shopping export [--format text\|markdown]` | The open list as plain text or a Markdown checklist |

A NAME that looks like a UUID is sent as a product id (`stock` commands). Units are `dl`,
`tsp`, `tbsp`, `g` and `pcs`; the server converts `l`, `kg` and the like on write.
Locations are `main_fridge`, `freezer` and `pantry`; priorities `urgent`, `normal` and
`low`. Every command has `-h` with examples.

The shopping commands call `/api/shopping/`:

| Command | Request | Exit codes beyond 0, 1, 2 and 7 |
| ------- | ------- | ------------------------------- |
| `shopping list` | `GET /api/shopping/?include_purchased=true&priority=P&limit=500&skip=N`, page after page | |
| `shopping add` | `POST /api/shopping/` `{name, quantity, unit, priority?, product_master_id?}` | 3 (unknown `--product-id`), 6 (reused key) |
| `shopping done` | `POST /api/shopping/{ID}/purchase?purchased=true\|false` | 3 (no such item), 6 (reused key) |
| `shopping remove` | `DELETE /api/shopping/{ID}`, no Idempotency-Key | 3 (no such item, also one already removed) |
| `shopping generate` | `POST /api/shopping/generate` `{sources: ["low_stock"], dry_run}` | 6; any 400 or 422 is 2 |
| `shopping export` | `GET /api/shopping/export?format=text\|markdown` | |

- `list` shows every item: the server answers at most 500 rows a request, so the CLI
  asks again with `skip` until a page comes back short.
- `add`: a blank NAME, or AMOUNT without UNIT (or the reverse), is a usage error (exit
  2) and nothing is sent. A free-text item without AMOUNT UNIT is 1 pcs. With
  `--product-id`, AMOUNT UNIT are required (exit 2 without them, nothing sent): a
  linked item's amount must be in the product's unit, or `generate` skips the item.
  Options may come anywhere on the line, also between NAME and AMOUNT (`shopping add
  milk --priority urgent 1 l`). An unknown `--product-id` (the server's foreign-key
  400) is `not_found`, exit 3.
- `done` and `remove` report a 404 as `not_found` (exit 3) only when it is the answer
  for a missing item: a coded `not_found`, or the router's `Shopping list item ID not
  found`. Any other 404 (a wrong route, a proxy's page) stays `http_404`, exit 1.
- `remove` sends no Idempotency-Key, because the server ignores it on DELETE: nothing
  could replay. Removing is safe to repeat instead. If a remove got no answer, run it
  again; exit 3 then means the first one removed it.

## Output

With `--json`, or whenever stdout is not a terminal, the CLI prints one JSON document on
stdout: the API's answer, or for an error its `detail` object (`{"code": ..., "message":
...}` plus any extra fields). Otherwise it prints short tables, and errors go to stderr.
When a name is ambiguous the candidates are printed in both modes.

Where the CLI adds to or builds the document itself:

- `stock add`, `stock consume`, `product name add`, `shopping add`, `shopping done`
  and `shopping generate` add `"replayed": true|false`: true when the server replayed
  the answer to an earlier request with the same Idempotency-Key instead of applying
  the change again.
- `shopping remove` answers 204 with no body; the JSON is `{"id": ..., "removed":
  true}`.
- `shopping export` is the exception to "JSON whenever stdout is not a terminal": it
  writes the server's text/plain or text/markdown body unchanged, to a terminal, a
  file or a pipe (`shopping export --format markdown > list.md`), and prints
  `{"format": ..., "text": ...}` only with an explicit `--json`. A success that is not
  text/plain or text/markdown (an HTML login page, JSON) is `bad_response`.
- `shopping generate` prints the backend's `{added, updated, unchanged, skipped,
  dry_run}` object; on a terminal it groups the products under those headings, with
  the reason for each skipped one.
- `doctor --json` prints `{"url": ..., "reachable": true, "name": ..., "scopes": [...],
  "auth_enabled": ...}`, from `/api/health/live` and `/api/whoami`.
- A usage error (bad arguments, no URL, a malformed URL or token) prints
  `{"code": "usage", "message": ...}` on stdout as well as the text on stderr.

Error codes the CLI makes up itself, next to the API's own (`not_found`, `ambiguous`,
`insufficient_stock`, `conflict`, `invalid`, `auth`):

| Code | Exit | Meaning |
| ---- | ---- | ------- |
| `usage` | 2 | bad arguments, no or a malformed URL, or a token it will not send |
| `connection` | 1 | could not connect (nothing was sent), or no answer to a read |
| `unknown_outcome` | 1 | a change was sent but no answer came; it may have been applied. The detail carries `idempotency_key` and `retry`, the exact command that replays it |
| `bad_response` | 1 | a success whose body is not the JSON expected (a proxy or login page, a wrong URL) |
| `unreachable` | 1 | `doctor`: `/api/health/live` answered with an error status |
| `http_<status>` | 1, 2 or 6 | an error without a coded detail; a 400 is exit 2, a 409 exit 6, anything else 1 |

## Retries

Mutations send an `Idempotency-Key`: by default the SHA-256 of the command line (less
`--url` and `--token` and their values, and the output-only `--json` and `--verbose`) and
the current UTC minute, so re-running the same command within the minute, with or
without those flags, does not add or consume twice. `--idempotency-key KEY` sets one
explicitly. A dry run sends none. The keyed mutations are `stock add`, `stock
consume`, `product name add`, `shopping add`, `shopping done` and `shopping generate`;
`shopping done ID` and `shopping done ID --undo` are different command lines, so they
get different keys. `shopping remove` sends no key (see above): a repeat is harmless and
exits 3.

When a change was sent but no answer came back (a read timeout), the CLI exits 1 with
`unknown_outcome`, prints the key it used and the command to retry with
`--idempotency-key`, so a retry after the minute boundary still replays instead of
applying twice.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | ok |
| 1 | error: cannot reach the server, a 5xx, an answer that is not the expected JSON, or a change sent that got no answer (it may have been applied) |
| 2 | usage: bad arguments, or the API rejected the request (400 invalid, 422) |
| 3 | not found: nothing matches the name, or no product has the id |
| 4 | ambiguous name: the candidates are printed on stdout |
| 5 | insufficient stock |
| 6 | conflict: the name belongs to another product, or a reused Idempotency-Key |
| 7 | auth: missing or unknown token (401), or a read token on a write (403) |

Exit 2 for a 400 `invalid` is the CLI's choice beyond the spec's "422 → 2": the server
understood the request and refused its content, which the caller must change, as with a
422. One exception: `stock add` with an unknown product id gets 400 `invalid` from the
server where `stock consume` gets 404 `not_found`; the CLI reports both as `not_found`,
exit 3.

## Development

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e './cli[dev]'
.venv/bin/python -m pytest cli/tests
.venv/bin/python cli/tests/regen_golden.py   # after changing any -h text
```
