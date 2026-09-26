# kyokki CLI

A command-line client for the Kyokki API, built for agents (and people) on the LAN.
It talks HTTP only; it shares no code with the backend.

## Install

```bash
pipx install ./cli          # or: pip install ./cli
export KYOKKI_URL=http://kyokki.lan:8000
export KYOKKI_TOKEN=...     # an API token from KYOKKI_API_TOKENS on the server
kyokki doctor
```

`--url` and `--token` override the environment. The token is only ever sent as the
`Authorization: Bearer` header; the CLI never prints it.

## Commands

| Command | What it does |
| ------- | ------------ |
| `kyokki doctor` | Reachability, then which token you are and whether auth is on |
| `kyokki stock list [--q NAME] [--location L] [--expiring DAYS] [--category ID]` | Stock per product, soonest to expire first |
| `kyokki stock add NAME QUANTITY [UNIT] [--category ID] [--location L] [--expiry DATE] [--purchased DATE]` | Add stock; a new product needs `--category` |
| `kyokki stock consume NAME AMOUNT UNIT [--location L] [--allow-partial] [--dry-run]` | Use up stock, first to expire first |
| `kyokki product resolve NAME` | What a name means: a match, candidates, or a suggestion |
| `kyokki product name add PRODUCT_ID NAME` | Teach a product another name |
| `kyokki category list` | Category ids for `--category` |

A NAME that looks like a UUID is sent as a product id. Units are `dl`, `tsp`, `tbsp`,
`g` and `pcs`; the server converts `l`, `kg` and the like on write. Locations are
`main_fridge`, `freezer` and `pantry`. Every command has `-h` with examples.

## Output

With `--json`, or whenever stdout is not a terminal, the CLI prints the API's JSON as
one document (for an error, the `detail` object). Otherwise it prints short tables.
When a name is ambiguous the candidates are printed in both modes.

## Retries

Mutations send an `Idempotency-Key`: by default the SHA-256 of the command line (less
`--url` and `--token` values) and the current UTC minute, so re-running the same command
within the minute does not add or consume twice. `--idempotency-key KEY` sets one
explicitly. A dry run sends none.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | ok |
| 1 | error: unreachable, server error, or an unexpected answer |
| 2 | usage: bad arguments, or the API rejected the request (400 `invalid`, 422) |
| 3 | not found |
| 4 | ambiguous name; the candidates are on stdout |
| 5 | insufficient stock |
| 6 | conflict |
| 7 | auth: missing or wrong token (401), or a read token on a write (403) |

## Development

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e './cli[dev]'
.venv/bin/python -m pytest cli/tests
.venv/bin/python cli/tests/regen_golden.py   # after changing any -h text
```
