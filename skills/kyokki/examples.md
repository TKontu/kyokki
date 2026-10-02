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

Dry-run it first and show the user what would be discarded:

```
kyokki stock discard --expired --dry-run
```

Then, once they confirm, discard it for real:

```
kyokki stock discard --expired
```

This is the iPad's expired shelf, in one tap: it discards every active item whose expiry
date is before today, by name rather than by item id. Each discard is logged
(`consumption_log`), can be undone with the general undo, and shows up on the Gone
screen. Narrow it to one place with `--location main_fridge|freezer|pantry` if that is
all the user asked about.

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

`--wait` can take up to ~30 minutes if the model has to re-read it; that is normal, not
a hang. Once it has read (completed), look at the lines, matched and not:

```
kyokki receipt status 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01
```

Say line 1, "KEVYTMAITO 1L", came back unmatched, with generic name "Milk". Teaching a
name (`product name add`) does not reach back into an already-read receipt, so resolve
and attach the line directly instead:

```
kyokki product resolve "Milk"
```

- A `match` (say product `0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01`): attach the line to it
  and confirm:
  ```
  kyokki receipt confirm 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --all-matched --assign 1=0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01
  ```
- `candidates` with no clear match (exit 4): ask the user which product they meant,
  then `--assign` it the same way. Never guess.
- No match at all, say line 2 "TUOREMEHU 1L" / generic "Juice": create a product for
  it, in a real category (`kyokki category list`), never an invented one:
  ```
  kyokki receipt confirm 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --all-matched --assign 1=0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --new 2=dairy
  ```

Confirm itself learns "KEVYTMAITO 1L" as Milk's alias and "TUOREMEHU 1L" as the new
Juice product's alias — no separate `product name add` needed for either.

If the user would rather decide about some lines later, send the rest now and leave
those out on purpose:

```
kyokki receipt confirm 0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01 --all-matched --skip-unmatched
```
