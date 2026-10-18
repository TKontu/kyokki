# Recipes — Development TODO

Planned 2026-10-18. Post-MVP frontier, item 15 of `docs/TODO.md` ("a recipes view inside the
fridge view", asked 2026-09-24) grows into this file.

## Rulings (operator, 2026-10-18)
- **Recipes are their own feature, not part of the agent track.** A backend and an iPad
  implementation in Kyokki. The agent uses the same HTTP API as the iPad does (AG1 tokens, AG2
  error shapes, idempotency keys); the `kyokki recipe` CLI commands and the skill text stay in
  `docs/agent_TODO.md` as a consumer of this API.
- **Recipes are stored natively in Kyokki** (Postgres, own tables, own screens). No Mealie or
  Tandoor: AG0 is dropped, AG5 is replaced by this file, and the recipe parts of
  `mealie_integration_TODO.md` are superseded.
- **Substitutions are a separate layer, never identity** (rules under RC6).

## Goal
From what is in storage, the kitchen can:
1. see which recipes it can cook now, and which use food that is about to expire;
2. see what a recipe is missing, and put exactly that on the shopping list;
3. when an ingredient is missing, get a sensible swap from what is in stock, confirm it, and
   have Kyokki remember it for that recipe;
4. cook a recipe and have the stock go down by what was used, with undo.

## Design principles
- **One behaviour, every surface.** The rules live in `app/services/recipes*.py`; the iPad, the
  agent (HTTP and CLI) and Home Assistant call the same endpoints. Layering as in `CLAUDE.md`.
- **An ingredient links to a generic product by an exact key only** (CL8,
  `docs/PRODUCT_IDENTITY_SPEC.md` "The rule", K1-K4). No similarity score, no model "is X the
  same as Y". An ingredient with no exact key stays *unlinked* and is shown as such; the cook
  links it explicitly. Candidates may be offered as **unticked suggestions** (CL8 ruling), and a
  link records its source like a join does, so it can be undone.
- **Recipe text is kept as written.** The ingredient's own name, amount and note are stored as
  imported; the product link sits next to them and never rewrites them.
- **Units follow DEC-1** (`dl | tsp | tbsp | g | pcs`), converted on write as stock is. `pcs`
  does not convert to weight (open question below).
- **Cooking is consumption.** A cook deducts through the existing consume service, so status,
  the opened clock, the consumption log, broadcasts, the min-stock check and the general undo
  all apply unchanged.
- **Mutations broadcast** over the WebSocket like inventory does (`recipe_update`).
- **No model work after a manual edit** (ruling 2026-10-09): the LLM is used only on an
  explicit request (import parsing, "suggest a swap"), never after the cook edits a recipe.

## Increments

### RC1 — Recipe model and API (backend, migration)
- Tables:
  - `recipe`: name, description, servings, total/active time, difficulty, tags, source
    (`manual | import`, source URL or project id), language, timestamps.
  - `recipe_section` (optional grouping, e.g. "Sauce") and `recipe_step`: order, text, timer as a
    range (min/max seconds), completion criterion (HowToCook "until the edges brown").
  - `recipe_ingredient`: recipe, optional step and section, order, name as written, amount,
    unit (DEC-1), note, `optional` flag, `product_master_id` (nullable), `link_source`
    (`exact_key | cook`), and `sub_recipe_id` (nullable) for a sauce or base that is its own
    recipe.
- CRUD: `GET/POST /api/recipes`, `GET/PATCH/DELETE /api/recipes/{id}`, servings scaling on read
  (`?servings=N`). Search by name and by product (`?q=`, `?product_id=`).
- Linking: `PUT /api/recipes/{id}/ingredients/{iid}/product {product_id | null}`; on create and
  import, exact keys link automatically (`link_source=exact_key`). A rename or a CL8 split of a
  product carries its links (they point at the product id), and a split asks nothing: links
  stay with the source product.
- Tests: the Karelian rule holds here too ("Karelian stew" never links to "Karelian pie"), a
  `tests/db/` only-head hand-off for the migration lane.

### RC2 — Import (backend)
- `POST /api/recipes/import {format, payload, dry_run}`: schema.org `Recipe` JSON-LD, and the
  translated HowToCook files from the operator's translation project (Markdown or JSON; the
  format is settled in this increment from three real files: a stir-fry, a soup and one with a
  sauce sub-recipe). Amounts from HowToCook's "Calculations" are kept exactly.
- A dry run returns the parsed recipe and the unlinked ingredients. Import never creates
  products.
- URL scraping is later, not here.

### RC3 — Availability: what can be cooked, what is missing (backend)
- `GET /api/recipes/cookable?servings=&strategy=all|expiring`: per recipe the share of
  ingredients in stock, and per ingredient `available | partial | missing | unlinked`, with the
  amount short. Optional ingredients do not count against it. `expiring` ranks recipes by how
  much soon-expiring stock they use, weighted by days left (the run-out and expiry data that
  already exist).
- "Cookable" counts **exact links only**. A swap (RC6) is reported beside it, never folded in:
  "90 %, or 100 % with one swap".

### RC4 — Cook (backend)
- `POST /api/recipes/{id}/cook {servings, dry_run, swaps, allow_partial}`: a dry run lists the
  deductions per inventory item (earliest expiry first) and the shortages; a real cook needs no
  shortage or `allow_partial`, runs in one transaction through the consume service, writes a
  `cooking_session` (recipe, servings, deductions, swaps used), broadcasts, and is undoable as
  one step through the general undo.
- `Idempotency-Key` honoured (agent retries).

### RC5 — Gaps to the shopping list (backend)
- `POST /api/shopping/generate` gains the source `recipe:{id, servings}` (several allowed).
  Settle the source shape first: today `sources: list[str]` answers 422 to an object
  (`agent_TODO.md`, AG6 note). Need per product minus stock on hand, merged into open rows with
  a source note, alongside `low_stock` and `runout`. Unlinked ingredients go on as free text.
- Meal plans (`meal_plan:{from,to}`) stay post-MVP backlog.

### RC6 — Substitutions (backend)
Rules (operator, 2026-10-18):
- **Never a product link.** A swap is "for this recipe's ingredient, use that product". It does
  not join products, does not create an alias or a learned name, and never touches
  `recipe_ingredient.product_master_id`.
- **Only when asked**: when a recipe is short, or when the cook asks "what can I use instead?"
  (`GET /api/recipes/{id}/ingredients/{iid}/swaps`). Order: swaps the cook confirmed before for
  this ingredient; then products in stock in the same category or a curated neighbour group
  (e.g. sour cream ↔ crème fraîche ↔ quark ↔ Greek yoghurt), preferring soon-expiring stock; then,
  on an explicit tap, a model proposal through the gateway (`settings`, no hardcoded model),
  which may only name products that are in stock.
- **The cook confirms; Kyokki remembers.** A confirmed swap is stored per recipe ingredient
  (`recipe_swap`: ingredient, product, amount ratio, confirmed at) and offered first next time.
  It can be forgotten. A cook (RC4) and a dry run deduct the swap's product.
- **Availability stays honest**: RC3 reports swaps separately.

### RC7 — iPad screens (frontend, owns `lib/i18n`)
- A Recipes screen in the app shell: list with search and the filters "Can cook now" and "Uses
  what's expiring"; each card shows its availability.
- A recipe page: servings stepper, ingredients with their state (in stock / short / missing /
  unlinked), steps with timers; "Link to a product" on an unlinked ingredient (unticked
  suggestions + search, CL8); "Swap…" on a short one (RC6); "Add missing to shopping"; "Cook"
  opens a dry-run sheet, then a toast with Undo.
- From the fridge: a way into "what can I cook with this" from an area or an item (item 15).
- Manual create and edit of a recipe; import from a file (RC2).
- Finnish and English UI text from the start (the display-language pattern); recipe text stays
  as written.
- `types/` mirror the RC1-RC6 schemas.

### Agent surface
The endpoints above are the agent's endpoints: AG1 scopes (`recipes:read`, `recipes:write`),
AG2's error shape, dry run, idempotency. The CLI commands
(`kyokki recipe search | show | can-cook [--expiring] | cook [--servings N] [--dry-run]`,
`shopping generate --from recipe`) and the skill text are an agent-track increment after RC4/RC5
(`docs/agent_TODO.md`, AG8).

## Order
```
RC1 model + API ─┬─> RC2 import
                 ├─> RC3 availability ─┬─> RC5 gaps to shopping
                 │                     └─> RC6 substitutions
                 └─> RC4 cook
RC7 iPad: starts after RC1's contract; grows with RC3-RC6
AG8 CLI + skill: after RC4 and RC5
```
Needs **CL8 L1** (exact keys) merged first: RC1's automatic linking uses the same key function.

## Open questions (decide in the named increment)
- RC1: `pcs` ingredients against weight stock ("2 tomatoes" vs 500 g): a per-product average
  piece weight, or ask at cook time.
- RC2: the HowToCook file format from the translation project.
- RC6: who curates the neighbour groups (shipped defaults vs this household's), and the
  ratio default (1:1 unless stated).
- RC7: Recipes as its own tab, or entered from the fridge only.
