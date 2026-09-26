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

A NAME that looks like a UUID is sent as a product id. Units are `dl`, `tsp`, `tbsp`,
`g` and `pcs`; the server converts `l`, `kg` and the like on write. Locations are
`main_fridge`, `freezer` and `pantry`. Every command has `-h` with examples.

## Output

With `--json`, or whenever stdout is not a terminal, the CLI prints one JSON document on
stdout: the API's answer, or for an error its `detail` object (`{"code": ..., "message":
...}` plus any extra fields). Otherwise it prints short tables, and errors go to stderr.
When a name is ambiguous the candidates are printed in both modes.

Where the CLI adds to or builds the document itself:

- `stock add`, `stock consume` and `product name add` add `"replayed": true|false`:
  true when the server replayed the answer to an earlier request with the same
  Idempotency-Key instead of applying the change again.
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
explicitly. A dry run sends none.

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
