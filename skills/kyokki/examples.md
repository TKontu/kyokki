# Kyokki: transcript-style examples

These follow the acceptance tasks from the agent track (AG7). Each shows the commands
you would actually run, in order.

## 1. "What do we have that expires this week?"

```
kyokki stock list --expiring 7
```

Read the rows marked `!`: those expire within 3 days or already have. Report the whole
list, soonest first, since "this week" is everything within 7 days.

## 2. "Add 2 packs of oat drink, 1 l each."

Resolve first — "oat drink" may already be a product or an alias:

```
kyokki product resolve "oat drink"
```

No match and no close candidate: create it (2 packs of 1 l is 2 l total), with a
category:

```
kyokki stock add "Oat drink" 2 l --category dairy
```

A match: add to the existing product by its id instead, so nothing is duplicated:

```
kyokki stock add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 2 l
```

## 3. "We used half a litre of milk."

```
kyokki stock consume milk 5 dl
```

(half a litre is 5 dl, Kyokki's canonical unit for liquids)

## 4. "Add a new product: tahini, pantry."

Resolve first, as always:

```
kyokki product resolve tahini
```

No match: create it in the pantry category, with a sensible starting amount if one was
given, 1 pcs otherwise:

```
kyokki stock add Tahini 1 pcs --category pantry --location pantry
```

## 5. "ARLA BARISTA is oat drink."

Resolve the generic product, then teach the printed name as its alias:

```
kyokki product resolve "oat drink"
kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 "ARLA BARISTA"
```

## 6. "Throw away everything expired."

Not available through the CLI yet: the agent-facing API has `stock list`, `stock add`
and `stock consume`, but no bulk discard-by-expiry endpoint (the iPad's discard lives at
`/api/inventory/discard`, which takes specific item ids and is not exposed to agents).
Tell the user this needs a follow-up on the backend before it can be automated, and
offer `kyokki stock list --expiring 0` so they can see what is already expired in the
meantime.

## 7. "What can I cook tonight with what's in the fridge?"

Needs recipes (AG5), not available yet.

## 8. "Cook the tomato egg stir-fry for 2" (dry run, confirm).

Needs recipes (AG5), not available yet.

## 9. "Make a shopping list for the tomato egg stir-fry and low stock."

The recipe half needs recipes (AG5), not available yet. The low-stock half works today:

```
kyokki shopping generate --from low-stock --dry-run
kyokki shopping generate --from low-stock
```

Show the dry run's `added`/`updated`/`skipped` groups to the user before running it for
real, then confirm what actually changed.

## 10. "Process this receipt" (file path), then confirm the matched lines.

```
kyokki receipt upload /path/to/receipt.jpg --wait
```

Once it has read (completed), look at the lines it could not match:

```
kyokki receipt status 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01
```

For each unmatched food line, resolve its name and either teach an alias (if it is a
known product under a new name) or create a product for it, then confirm:

```
kyokki product resolve "KEVYTMAITO 1L"
kyokki product name add 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 "KEVYTMAITO 1L"
kyokki receipt confirm 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --all-matched
```

If the user would rather decide about the rest later, send the matched lines now and
ask about the others separately — never guess a match yourself:

```
kyokki receipt confirm 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --all-matched --skip-unmatched
```
