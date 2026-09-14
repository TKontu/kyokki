# Agent interface — Development TODO

Planned 2026-09-14. **Starts after MVP-P3** (operator ruling). Nothing here enters an MVP wave.

## Goal
A Hermes Agent or OpenClaw agent runs the kitchen through Kyokki the way a person would:
- adds and consumes stock;
- creates generic products and teaches store names;
- explores and cooks recipes;
- builds the shopping list.

## Rulings (2026-09-14)
- **No MCP server.** Agents use the **HTTP API**, a thin **`kyokki` CLI** with thorough `-h`
  help and JSON output, and a **`SKILL.md`**.
  - Hermes Agent and OpenClaw both load SKILL.md skills (AgentSkills format).
- **Agent use is post-MVP.** The whole track waits for the iPad acceptance week (MVP-P3).
- **"Product variants" means new generic products plus aliases.** The generic-product ruling of
  MVP-R2 stands: no brand, fat content or cut variants. An agent creates "Oat drink" and teaches
  names that map to it ("ARLA BARISTA", "kaurajuoma").
- **Recipes live in an existing recipe service if one fits.** The operator leans towards Mealie
  or an alternative, and would rather not maintain a native recipe model. The requirement is
  HowToCook-level granularity. AG0 decides.

## Where we are today
The API is usable by an agent already, but it was built for the iPad screens.

| Need | Today | Gap |
| --- | --- | --- |
| Read stock | `GET /api/inventory` (per item, UUIDs) | No per-product summary ("how much milk, earliest expiry"), no name filter |
| Add stock | `POST /api/inventory/quick-add` (by name, MVP-S3) | No idempotency key, so an agent retry adds twice |
| Consume | `POST /api/inventory/{id}/consume` | Needs an item UUID; no "consume 2 dl milk" across items; no unit conversion or dry run |
| Products | `GET/POST /api/products` | No "resolve this name" with candidates and confidence, so agents create duplicates; no alias API (aliases are learned only on receipt confirm) |
| Receipts | upload, queue, confirm | Usable, but confirm needs line indexes from a GET first |
| Shopping list | CRUD + purchase (`/api/shopping`) | No generation from low stock or recipes; no link from purchase to stock |
| Recipes | none (`mealie_integration_TODO.md` is unbuilt) | Everything |
| Auth | none; the API is open on the LAN | Agents on another host need tokens; the iPad must keep working |
| Discoverability | OpenAPI at `/docs` | Errors are free text, with no stable codes, candidates or next steps |

## Design principles
- **One behaviour, three surfaces.** Rules live in backend services, as `generic_products.py`
  and `receipt_confirm.py` already do. The iPad, the HTTP API, the CLI and a later Home Assistant
  integration all call them. The CLI holds no business logic.
- **Names in, decisions out.** Agents speak in names and amounts ("2 dl milk"). Endpoints resolve
  names and return what they did: which items were deducted, and what is left.
- **Ambiguity is an answer, not a guess.** When a name matches several products, respond
  `409 ambiguous` with ranked `candidates`. The agent asks the user or picks one explicitly.
- **Safe to retry.** Every mutation accepts an `Idempotency-Key` header; a repeated key returns
  the first result.
- **Dry run everywhere.** `dry_run=true` returns the planned effect without writing: consume,
  cook, generate shopping list.
- **Stable, machine-readable errors:** `{"code": "not_found|ambiguous|insufficient_stock|invalid|conflict", "message": "...", "candidates": [...], "hint": "..."}`.
  The CLI maps them to exit codes.
- **Units** follow DEC-1: `dl | tsp | tbsp | g | pcs`, converting on write. Recipe amounts
  convert the same way. `pcs` does not convert to weight.

## Increments

### AG0 — Recipe backend decision (spike, operator-gated)
Import 3 translated HowToCook recipes into **Mealie** and **Tandoor**, then compare them with the
criteria below. The recipes are a stir-fry, a soup and something with a sub-recipe or sauce, from
the operator's translation project.
- **Granularity:**
  - HowToCook's "Calculations" section gives exact grams or millilitres per serving.
  - "Operations" gives steps with exact amounts and completion criteria, and timings as ranges.
  - The service must store per-ingredient amount, unit and food, ingredients per step,
    servings scaling, step timers, sections, tools, and a difficulty rating (a tag or custom
    field is fine).
  - Mealie links ingredients to steps and stores quantity/unit/food/note per ingredient.
  - Tandoor models ingredients inside steps (`steps[].ingredients[]`) and supports sub-recipes.
  - Verify both hands-on; don't trust the docs alone.
- **Import:** bulk import of the translated Markdown or JSON through the REST API, without
  losing amounts.
- **Food mapping:** the service's food names can be mapped to Kyokki generic products (English
  names), and the mapping survives re-imports.
- **API:** token auth, search by name and by ingredient, and read recipes with structured
  ingredients.
- **Ops:** runs on the homelab stack (its own Postgres database or SQLite), plus the backup story.
- **Licence** (checked 2026-09-14): both allow free self-hosting and integration over their HTTP
  APIs. Kyokki runs them unmodified as separate services and never copies their code, so neither
  licence reaches Kyokki's own code.
  - **Mealie:** AGPL-3.0. Modifying Mealie and offering it over a network requires publishing
    those changes.
  - **Tandoor:** AGPL-3.0 with a Commons Clause selling restriction. Selling the software, or a
    paid hosting or support service whose value comes substantially from it, is not allowed. It
    is therefore not OSI open source, although personal self-hosting is explicitly free.
  - Only matters if Kyokki were ever sold as a hosted product bundling Tandoor.
- **Fallback:** a thin native model in Kyokki (recipe, step, ingredient) only if neither service
  holds the granularity. The operator prefers to avoid this.
- **Output:** a filled comparison table in this file, and the operator's pick. AG5 follows it.

### AG1 — Agent access tokens
- `KYOKKI_API_TOKENS`: named tokens with scopes (`read`, `write`), e.g.
  `hermes:write:<secret>`. Store only hashes, and never log a token.
- `Authorization: Bearer <token>` on `/api/*`. Without tokens configured the API behaves as
  today, so LAN development still works.
- **The iPad keeps working without a login.** The Next.js server proxy adds a server-side token
  on `/api/*` (middleware), so the browser never holds one.
  - Alternatively, keep same-origin proxy traffic exempt.
  - Decide inside AG1; the proxy-token route is preferred.
- `GET /api/whoami` returns the token name and scopes. The CLI uses it for `kyokki doctor`.
- **Tests:** missing, invalid, read-only token on a write, the proxy path, and no token when auth
  is disabled.

### AG2 — Stock and product endpoints for agents
All of these are thin endpoints over services, shared with the iPad where the behaviour matches.
- **`GET /api/stock`** gives a per-product summary: product, category, total per unit, item count,
  earliest expiry, location breakdown and expiring flags. Filters: `q` (name, alias-aware),
  `location`, `expiring_days`, `category`.
- **`POST /api/stock/add`** is quick add (MVP-S3) plus `Idempotency-Key`. It accepts an
  optional `receipt_id` and `notes`.
- **`POST /api/stock/consume`** takes `{product | product_id, amount, unit, location?, dry_run?}`:
  - It allocates FIFO by earliest expiry across that product's active items.
  - It converts units where they are compatible.
  - It returns the per-item deductions and what remains.
  - Not enough stock → `409 insufficient_stock` with the available amount (partial consume only
    with `allow_partial=true`).
  - The iPad's ConsumptionSheet keeps using per-item consume.
- **`GET /api/products/resolve?name=`** returns `{match | null, candidates[{product, score, source}], suggestion}`.
  It reuses `MatchingService` (alias, exact, generic, fuzzy).
- **`POST /api/products/{id}/aliases`** takes `{name, store_chain?}` and upserts a verified
  alias, reusing the R2 alias logic. **`GET`** lists aliases, and **`DELETE`** removes a wrong one.
- **Product create** goes through `ProductResolver` (case-insensitive reuse, category defaults).
  An exact duplicate returns the existing product with `created: false`.
- **Idempotency:** an `idempotency_key` table (key, route, request hash, response, 24 h TTL) and a
  small dependency used by all agent mutations.
- **Errors:** a shared exception handler for the error shape above on these routes.
- **Tests:**
  - FIFO allocation across items with different expiries.
  - Unit conversion (`l → dl`), incompatible units (`pcs` vs `g`), insufficient stock, dry run
    writing nothing.
  - An ambiguous name giving candidates.
  - A repeated idempotency key, and the same key with a different body (`409 conflict`).

### AG3 — `kyokki` CLI
A Python package in `cli/`, installable with `pipx install ./cli` on the agent host. It uses
httpx plus argparse or Typer, with no backend imports.
- **Config:** `KYOKKI_URL` and `KYOKKI_TOKEN` (or `--url`/`--token`).
- **`kyokki doctor`** checks reachability, the token and its scopes.
- **Output:** JSON when stdout is not a TTY or `--json` is given; short tables for humans
  otherwise. `--dry-run` on every mutation. `--idempotency-key` is optional; by default the CLI
  derives one per invocation, so a shell retry of the same command line within a minute is safe.
- **Exit codes:**

  | Code | Meaning |
  | --- | --- |
  | 0 | ok |
  | 1 | error |
  | 2 | usage |
  | 3 | not found |
  | 4 | ambiguous (candidates on stdout) |
  | 5 | insufficient stock |
  | 6 | conflict |
  | 7 | auth |
- **Commands** (every `-h` shows purpose, arguments with units, 2–3 examples and exit codes):
  ```
  kyokki stock list [--q NAME] [--location fridge|freezer|pantry] [--expiring DAYS]
  kyokki stock add NAME AMOUNT UNIT [--category ID] [--location L] [--expiry DATE]
  kyokki stock consume NAME AMOUNT UNIT [--location L] [--allow-partial] [--dry-run]
  kyokki stock discard ITEM_ID | --expired
  kyokki product resolve NAME
  kyokki product create NAME --category ID [--unit U]
  kyokki product alias add PRODUCT NAME [--store CHAIN]
  kyokki category list
  kyokki receipt upload FILE ; kyokki receipt status ID ; kyokki receipt confirm ID --all-matched
  kyokki shopping list | add NAME [AMOUNT UNIT] | done ID | generate --from low-stock|recipe SLUG
  kyokki recipe search QUERY | show SLUG | can-cook [--expiring] | cook SLUG [--servings N] [--dry-run]
  ```
- **Tests:**
  - Golden `-h` snapshots.
  - Every command against a mocked HTTP layer (respx or MockTransport).
  - Exit code mapping, JSON output schema, and that the token never appears in output.

### AG4 — Kyokki skill for Hermes and OpenClaw
- `skills/kyokki/SKILL.md` in the AgentSkills format, with name and description frontmatter.
  Installable with `hermes skills install TKontu/kyokki/skills/kyokki` and copyable to OpenClaw.
- **Contents:**
  - What Kyokki is and the generic-product rule.
  - Setup: `pipx`, the env vars, `kyokki doctor`.
  - **Workflows with exact commands:**
    - Resolve before create.
    - Consume by name, with a dry run for big amounts.
    - On exit 4 (ambiguous), ask the user or pick a candidate.
    - "What's expiring?"
    - Receipt: upload, poll, confirm the matched lines, ask about the rest.
    - Shopping list generation.
    - Cook a recipe with a dry run, then confirm.
  - Units and conversions.
  - What never to do: delete products, consume without resolving on exit 4, invent categories.
- `skills/kyokki/examples.md` has transcript-style examples. Keep SKILL.md short so it loads
  cheaply.
- **Acceptance:** a scripted run with Hermes Agent against a staging stack completes 10 tasks
  (list below) without human correction. Record the transcript in this file.

### AG5 — Recipes (after AG0)
Adapter module `app/integrations/recipes/` behind a `RecipeSource` interface (Mealie or Tandoor
client), so the choice stays swappable.
- **Food mapping:** the recipe service's food is mapped to a Kyokki generic product.
  - The mapping is stored in Kyokki (`recipe_food_map`: source food id → `product_master_id`,
    verified flag).
  - It is auto-proposed with `MatchingService`, and unmapped foods are listed for the agent or
    user to map.
- **Endpoints:**
  - `GET /api/recipes?q=&ingredient=` and `GET /api/recipes/{slug}` (normalised ingredients in
    canonical units, steps).
  - `GET /api/recipes/cookable` gives the availability percentage per recipe, with missing
    ingredients.
  - `GET /api/recipes/suggestions?strategy=expiring` ranks recipes that use soon-expiring stock.
  - `POST /api/recipes/{slug}/cook {servings, dry_run}` consumes through AG2's consume for each
    ingredient in one transaction:
    - a dry run shows deductions and shortages;
    - a real cook needs no shortages or `allow_partial`;
    - it writes a `cooking_session` record.
- **HowToCook import** happens in the operator's translation project, through the recipe
  service's API. Kyokki only reads.
- This supersedes the recipe parts of `mealie_integration_TODO.md`; its meal-plan parts stay
  post-MVP backlog.

### AG6 — Shopping list extraction
- **`POST /api/shopping/generate {sources: [low_stock | recipe:{slug, servings} | meal_plan:{from,to}], dry_run}`:**
  - Needs are computed per generic product and stock on hand is subtracted.
  - They merge into existing open items (no duplicates), with a `source` note per line.
  - Low stock uses `product_master.min_stock_quantity` / `reorder_quantity`.
- **`POST /api/shopping/{id}/purchase`** optionally adds to stock (`add_to_stock: true`, quick-add
  rules). Receipts remain the main path.
- **Export:** `GET /api/shopping/export?format=text|markdown` gives a clean list for the agent to
  send to Telegram or elsewhere.

### AG7 — Agent acceptance
A staging stack with seeded data and the Hermes Agent skill installed. Tasks, all by natural
language:
1. "What do we have that expires this week?"
2. "Add 2 packs of oat drink, 1 l each."
3. "We used half a litre of milk."
4. "Add a new product: tahini, pantry."
5. "ARLA BARISTA is oat drink."
6. "Throw away everything expired."
7. "What can I cook tonight with what's in the fridge?"
8. "Cook the tomato egg stir-fry for 2" (dry run, confirm).
9. "Make a shopping list for the tomato egg stir-fry and low stock."
10. "Process this receipt" (file path), then confirm the matched lines.

Record the pass/fail and any friction here, and fix it before calling the track done.

## Order and dependencies
```
AG1 tokens ─┬─> AG2 stock/product endpoints ─> AG3 CLI ─> AG4 skill ─┐
            │                                                        ├─> AG7 acceptance
AG0 recipe decision ─> AG5 recipes ─> AG6 shopping generation ───────┘
```
AG0 can run in parallel with AG1–AG4. AG6's `low_stock` source does not need recipes and can
ship before AG5.

## Open questions (decide in the named increment)
- AG1: the agent host. Is Hermes or OpenClaw on the homelab network or remote? Remote access
  needs HTTPS (Traefik, post-MVP item 4) or a tunnel.
- AG0: recipe service choice, and whether difficulty or calories need custom fields.
- AG2: whether consume should also mark items `opened` (post-MVP "Opened tracking").
- AG5: how cooking handles `pcs` ingredients against weight stock (e.g. "2 tomatoes" vs 500 g).
  Options are a per-product average piece weight, or asking.
