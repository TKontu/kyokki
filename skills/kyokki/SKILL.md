---
name: kyokki
description: Manage the Kyokki kitchen inventory (stock, products, receipts, shopping list) over HTTP through the kyokki CLI, on the local network. Use whenever asked to check, add, consume or shop for kitchen stock, or to process a receipt.
---

# Kyokki

Kyokki is a self-hosted kitchen inventory system. You drive it entirely through the
`kyokki` CLI over HTTP — there is no MCP server.

## The generic-product rule

Kyokki holds **one product per food**, named plainly ("Milk", "Oat drink", "Tahini") —
never a brand, size, fat content or cut. A name as printed on a receipt or asked by
a person ("ARLA BARISTA", "kaurajuoma") is an *alias* that resolves to the generic
product; it is never a product of its own. Always resolve a name before creating
anything.

## Setup

```
pipx install ./cli
export KYOKKI_URL=http://<homelab>:17300
export KYOKKI_TOKEN=<your token>
kyokki doctor
```

`kyokki doctor` confirms the server is reachable and which token you are. Every command
has `-h` with its arguments, units, examples and exit codes — read it when unsure of one.

## Exit codes you must branch on

`0` ok · `1` error · `2` usage · `3` not found · `4` ambiguous · `5` insufficient stock ·
`6` conflict · `7` auth. Full table: `kyokki -h`.

## Workflows

### Resolve before you create

Never add stock for a name you have not resolved first — it may already be an alias.

```
kyokki product resolve "oat milk"
```

- A `match` → use its `product_id`.
- `candidates` with no `match` → ask the user which one they meant, or pick the best
  one explicitly; never guess silently.
- Neither → create it, with a category:

```
kyokki stock add "Oat drink" 1 l --category dairy
```

Then teach the printed name as an alias, so next time resolves cleanly:

```
kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 "ARLA BARISTA"
```

### Consume by name

```
kyokki stock consume milk 2 dl
```

For a large amount, dry-run it first and show the user what would happen before
sending it for real:

```
kyokki stock consume milk 2 l --dry-run
```

### Exit 4: ambiguous

A name lookup (`stock consume`, `stock add`) exits 4 when it is close to more than one
product, printing the candidates on stdout. **Never guess and never retry blindly.** Ask
the user which one they meant, or resolve the name and act on its exact `product_id`:

```
kyokki product resolve "kevytmaito"
```

### What's expiring?

```
kyokki stock list --expiring 3
```

### A receipt

```
kyokki receipt upload receipt.jpg --wait
kyokki receipt status 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01
```

`--wait` polls until the model has read it — a receipt can take up to ~30 minutes
when the model re-reads it, so the default `--timeout` is generous; do not shorten it.
`status` lists each line, its printed and generic name, and the matched product (or
`(unmatched)`).

`confirm --all-matched` sends every matched food line as-is. **Teaching a name
(`product name add`) never touches a receipt already read** — it does not fix an
unmatched line, so do not loop on it. For each unmatched line, resolve its generic name
(`kyokki product resolve "<name>"`), then: one clear `match` → attach the line to it
with `--assign`; `candidates`, no clear match (exit 4) → ask the user, then `--assign`
the one they pick; no match at all → `--new` it, in a real category from
`kyokki category list` (never invent one):

```
kyokki receipt confirm 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --all-matched --assign 1=0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --new 2=pantry
```

`--assign`/`--new` are repeatable, one per unmatched line, and combine with a plain
`--all-matched`. Only leave a line out on purpose, with `--skip-unmatched`; confirm is
final, and a line you do not send is never stocked. Confirm itself already learns the
line's printed name as an alias for next time — no separate `product name add` needed
for a line you just confirmed.

### Shopping list

```
kyokki shopping generate --dry-run
kyokki shopping generate
```

Fills the list from what the kitchen is short of. Add a one-off item freely:

```
kyokki shopping add "dish soap"
```

Export it to send elsewhere:

```
kyokki shopping export --format markdown
```

### Recipes

Not available yet (waits for AG5) — the CLI has no recipe command. Say so rather than
improvising one.

## Units and conversions

`dl`, `tsp`, `tbsp`, `g`, `pcs`. Give amounts in whatever unit the person used; the
server converts `l`, `kg` and the like to these on write. `pcs` never converts to
weight.

## Never

- **Never delete a product.** There is no delete command, on purpose: it would orphan
  stock history. If a product is wrong, teach it names, or ask the operator.
- **Never consume past an exit-4 ambiguity.** Resolve the name, or ask, first.
- **Never invent a category.** Use one from `kyokki category list`.

See `examples.md` for transcript-style walkthroughs.
