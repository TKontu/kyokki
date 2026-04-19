# Mealie Integration Module — Development TODO

## Module Overview
**Integration Target:** Mealie (self-hosted recipe manager, v2.x)  
**Location:** `/backend/app/integrations/mealie/`  
**Frontend Location:** `/frontend/src/components/recipes/`, `/frontend/src/app/recipes/`  
**Primary Responsibilities:**
- Recipe retrieval and search via Mealie REST API
- Ingredient-to-inventory matching ("can I cook this?")
- Expiry-aware recipe suggestions ("use it or lose it")
- Inventory deduction when cooking a recipe
- Meal plan sync and shopping list bridge
- HowToCook recipe import pipeline (batch)

**Design Principle:** Mealie owns recipes, Fridge Logger owns inventory.  
Data flows through a thin mapping layer — no bidirectional database sync.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Fridge Logger System                            │
│                                                                         │
│  ┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐  │
│  │   Frontend    │────▶│  FastAPI Backend  │────▶│    PostgreSQL      │  │
│  │  (iPad PWA)   │◀────│  /api/recipes/*   │◀────│                    │  │
│  │               │     │                  │     │  ingredient_map    │  │
│  │ Recipe views  │     │  recipe_service  │     │  cooking_session   │  │
│  │ Cook mode     │     │  mealie_client   │     │  meal_plan_cache   │  │
│  │ Meal planner  │     │  matching_svc    │     │                    │  │
│  └──────────────┘     └────────┬─────────┘     └────────────────────┘  │
│                                │                                        │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │ HTTP (internal network)
                                 ▼
                    ┌──────────────────────┐
                    │   Mealie Instance     │
                    │   (Docker, port 9000) │
                    │                      │
                    │  • Recipe database    │
                    │  • Foods & units      │
                    │  • Meal plans         │
                    │  • Shopping lists     │
                    │  • Ollama integration │
                    └──────────────────────┘
```

### Data Flow Patterns

```
READ: "What can I cook?"
  iPad → GET /api/recipes/cookable
       → recipe_service queries Mealie for recipes
       → matching_service compares ingredients against inventory
       → returns ranked list with availability %

READ: "Use expiring items"
  iPad → GET /api/recipes/suggestions?strategy=expiring
       → recipe_service gets expiring inventory items
       → queries Mealie for recipes containing those foods
       → returns recipes sorted by expiry coverage

WRITE: "I'm cooking this"
  iPad → POST /api/recipes/{mealie_id}/cook
       → recipe_service fetches full recipe from Mealie
       → deducts matched ingredients from inventory
       → creates cooking_session log
       → broadcasts inventory update via WebSocket

SYNC: Meal plan
  Celery beat → fetch Mealie meal plan weekly
             → cache locally for fast frontend access
             → pre-compute ingredient availability
```

---

## Directory Structure (Target)

```
backend/app/
├── integrations/
│   └── mealie/
│       ├── __init__.py
│       ├── client.py              # Mealie API client (httpx async)
│       ├── schemas.py             # Pydantic models for Mealie responses
│       ├── config.py              # Mealie connection settings
│       └── exceptions.py          # Mealie-specific error types
│
├── models/
│   ├── ... (existing)
│   ├── ingredient_map.py          # MealieFood ↔ ProductMaster mapping
│   └── cooking_session.py         # Cooking event log
│
├── services/
│   ├── ... (existing)
│   ├── recipe_service.py          # Recipe business logic
│   └── ingredient_matching.py     # Recipe ingredient ↔ inventory matching
│
├── api/
│   ├── routes/
│   │   ├── ... (existing)
│   │   └── recipes.py             # Recipe API endpoints
│   └── schemas/
│       ├── ... (existing)
│       └── recipes.py             # Request/response schemas
│
└── tasks/
    ├── ... (existing)
    └── mealie_tasks.py            # Sync, cache, import tasks

frontend/src/
├── app/
│   ├── ... (existing)
│   └── recipes/
│       ├── page.tsx               # Recipe browser
│       ├── [id]/
│       │   └── page.tsx           # Recipe detail + cook mode
│       └── meal-plan/
│           └── page.tsx           # Weekly meal plan view
│
├── components/
│   ├── ... (existing)
│   └── recipes/
│       ├── RecipeCard.tsx          # Recipe summary card
│       ├── RecipeDetail.tsx        # Full recipe with cook actions
│       ├── IngredientList.tsx      # Ingredients with availability
│       ├── AvailabilityBadge.tsx   # % of ingredients in stock
│       ├── CookButton.tsx          # Start cooking action
│       ├── RecipeFilter.tsx        # Filter/search controls
│       ├── MealPlanWeek.tsx        # Weekly meal plan grid
│       └── SuggestionPanel.tsx     # "Use expiring items" panel
│
├── hooks/
│   ├── ... (existing)
│   ├── useRecipes.ts              # Recipe data + mutations
│   └── useMealPlan.ts             # Meal plan data
│
└── types/
    ├── ... (existing)
    └── recipe.ts                  # Recipe type definitions
```

---

## Phase 1: Foundation — Mealie Client & Data Bridge

**Goal:** Working connection to Mealie, ingredient mapping, basic recipe queries  
**Prerequisites:** Fridge Logger Phase 1 complete (inventory + products working)  
**Estimated Duration:** 2 weeks

### 1.1 Infrastructure — Mealie Deployment

- [ ] Add Mealie to `docker-compose.yml`
  ```yaml
  mealie:
    image: ghcr.io/mealie-recipes/mealie:v2.6.0
    container_name: mealie
    environment:
      PUID: 1000
      PGID: 1000
      TZ: Europe/Helsinki
      MAX_WORKERS: 1
      WEB_CONCURRENCY: 1
      # Use Fridge Logger's Postgres
      DB_ENGINE: postgres
      POSTGRES_USER: ${MEALIE_POSTGRES_USER}
      POSTGRES_PASSWORD: ${MEALIE_POSTGRES_PASSWORD}
      POSTGRES_SERVER: postgres
      POSTGRES_PORT: 5432
      POSTGRES_DB: mealie
      # Ollama integration
      OPENAI_BASE_URL: http://192.168.0.247:11434/v1
      OPENAI_API_KEY: "ollama"
      OPENAI_MODEL: "qwen2-vl:7b"
      OPENAI_SEND_DATABASE_DATA: "true"
      OPENAI_ENABLE_IMAGE_SERVICES: "true"
    volumes:
      - mealie_data:/app/data
    networks:
      - fridge-net
    depends_on:
      - postgres
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.mealie.rule=Host(`mealie.local`)"
      - "traefik.http.routers.mealie.tls=true"
      - "traefik.http.services.mealie.loadbalancer.server.port=9000"
  ```
- [ ] Add `mealie` database to Postgres init script
- [ ] Add Mealie environment variables to `.env.example`
  ```env
  # Mealie
  MEALIE_POSTGRES_USER=mealie_user
  MEALIE_POSTGRES_PASSWORD=your_secure_password
  MEALIE_URL=http://mealie:9000
  MEALIE_API_TOKEN=your_api_token
  ```
- [ ] Verify Mealie starts and is accessible
- [ ] Create Mealie API token via initial web setup
- [ ] Verify Ollama connectivity from Mealie container
- [ ] Seed Mealie with Foods and Units (Finnish locale)
- [ ] Add Mealie health check to `/api/health` endpoint

### 1.2 Mealie API Client

**File:** `integrations/mealie/client.py`

- [ ] Async HTTP client using httpx
  ```python
  class MealieClient:
      def __init__(self, base_url: str, api_token: str):
          self.base_url = base_url.rstrip("/")
          self.client = httpx.AsyncClient(
              base_url=self.base_url,
              headers={"Authorization": f"Bearer {api_token}"},
              timeout=30.0,
          )
  ```
- [ ] **Recipe methods**
  - [ ] `get_recipes(page, per_page, search, categories, tags)` — paginated list
  - [ ] `get_recipe(slug_or_id)` — full recipe with ingredients
  - [ ] `search_recipes(query)` — text search
  - [ ] `get_recipes_by_food(food_id)` — recipes containing a specific food
  - [ ] `create_recipe(data)` — create from structured data
  - [ ] `import_recipe_url(url)` — import from URL via Mealie scraper
  - [ ] `import_recipe_image(image_bytes)` — import from photo via Ollama
- [ ] **Food/ingredient methods**
  - [ ] `get_foods(page, per_page, search)` — list all foods
  - [ ] `get_food(food_id)` — single food detail
  - [ ] `create_food(name, label_id)` — create new food entry
  - [ ] `get_units()` — list measurement units
- [ ] **Meal plan methods**
  - [ ] `get_meal_plans(start_date, end_date)` — date range query
  - [ ] `create_meal_plan(date, entry_type, recipe_id)` — add to plan
  - [ ] `delete_meal_plan(plan_id)` — remove from plan
- [ ] **Shopping list methods**
  - [ ] `get_shopping_lists()` — list all lists
  - [ ] `get_shopping_list(list_id)` — list with items
  - [ ] `add_shopping_list_item(list_id, food_id, quantity, unit_id)` — add item
- [ ] Connection pooling and retry logic
- [ ] Graceful degradation when Mealie is unavailable
- [ ] Response caching (short TTL for recipe lists, longer for food DB)
- [ ] Rate limiting (respect Mealie's capacity)

**File:** `integrations/mealie/schemas.py`

- [ ] Pydantic models for Mealie API responses
  ```python
  class MealieFood(BaseModel):
      id: UUID
      name: str
      label: Optional[MealieLabel] = None
      extras: dict = {}

  class MealieRecipeIngredient(BaseModel):
      quantity: Optional[float] = None
      unit: Optional[MealieUnit] = None
      food: Optional[MealieFood] = None
      note: str = ""
      is_food: bool = True
      original_text: Optional[str] = None

  class MealieRecipeSummary(BaseModel):
      id: UUID
      slug: str
      name: str
      description: Optional[str] = None
      image: Optional[str] = None
      total_time: Optional[str] = None
      prep_time: Optional[str] = None
      cook_time: Optional[str] = None
      recipe_yield: Optional[str] = None
      tags: list[MealieTag] = []
      recipe_category: list[MealieCategory] = []
      rating: Optional[float] = None
      last_made: Optional[datetime] = None

  class MealieRecipe(MealieRecipeSummary):
      recipe_ingredient: list[MealieRecipeIngredient] = []
      recipe_instructions: list[MealieRecipeInstruction] = []
      nutrition: Optional[MealieNutrition] = None
      org_url: Optional[str] = None

  class MealieMealPlanEntry(BaseModel):
      id: int
      date: date
      entry_type: str  # "breakfast" | "lunch" | "dinner" | "side"
      recipe: Optional[MealieRecipeSummary] = None
      title: Optional[str] = None
  ```

**File:** `integrations/mealie/config.py`

- [ ] Mealie settings in pydantic-settings
  ```python
  class MealieSettings(BaseSettings):
      MEALIE_URL: str = "http://mealie:9000"
      MEALIE_API_TOKEN: str = ""
      MEALIE_ENABLED: bool = True
      MEALIE_CACHE_TTL_RECIPES: int = 300   # 5 min
      MEALIE_CACHE_TTL_FOODS: int = 3600    # 1 hour
      MEALIE_TIMEOUT: int = 30

      model_config = SettingsConfigDict(env_file=".env")
  ```

**File:** `integrations/mealie/exceptions.py`

- [ ] `MealieConnectionError` — cannot reach Mealie
- [ ] `MealieAuthError` — invalid or expired token
- [ ] `MealieNotFoundError` — recipe/food not found
- [ ] `MealieUnavailableError` — Mealie is down, graceful fallback

### 1.3 Ingredient Mapping — Database Layer

**File:** `models/ingredient_map.py`

- [ ] `IngredientMap` model
  ```python
  class IngredientMap(Base):
      """Maps Mealie food items to Fridge Logger product_master entries.
      Similar pattern to store_product_alias — one Mealie food can map
      to multiple products, and vice versa."""

      __tablename__ = "ingredient_map"

      id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
      mealie_food_id: Mapped[UUID] = mapped_column(index=True)
      mealie_food_name: Mapped[str]  # denormalized for display
      product_master_id: Mapped[UUID] = mapped_column(
          ForeignKey("product_master.id"), index=True
      )
      confidence_score: Mapped[float] = mapped_column(default=0.0)
      manually_verified: Mapped[bool] = mapped_column(default=False)
      created_at: Mapped[datetime] = mapped_column(default=func.now())
      updated_at: Mapped[datetime] = mapped_column(
          default=func.now(), onupdate=func.now()
      )

      # Relationships
      product_master: Mapped["ProductMaster"] = relationship()
  ```

- [ ] `CookingSession` model
  ```python
  class CookingSession(Base):
      """Log of recipes cooked — for learning and analytics."""

      __tablename__ = "cooking_session"

      id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
      mealie_recipe_id: Mapped[UUID]
      mealie_recipe_name: Mapped[str]         # denormalized
      mealie_recipe_slug: Mapped[str]         # for linking back
      servings_cooked: Mapped[float] = mapped_column(default=1.0)
      context: Mapped[str] = mapped_column(    # breakfast|lunch|dinner|other
          default="dinner"
      )
      ingredients_deducted: Mapped[dict] = mapped_column(
          JSONB, default=dict
      )  # snapshot: {inventory_item_id: quantity_used}
      ingredients_missing: Mapped[dict] = mapped_column(
          JSONB, default=dict
      )  # {mealie_food_name: quantity_needed}
      cooked_at: Mapped[datetime] = mapped_column(default=func.now())
  ```

- [ ] `MealPlanCache` model
  ```python
  class MealPlanCache(Base):
      """Local cache of Mealie meal plan for fast frontend access."""

      __tablename__ = "meal_plan_cache"

      id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
      mealie_plan_id: Mapped[int] = mapped_column(unique=True)
      plan_date: Mapped[date] = mapped_column(index=True)
      entry_type: Mapped[str]               # breakfast|lunch|dinner|side
      mealie_recipe_id: Mapped[Optional[UUID]]
      mealie_recipe_slug: Mapped[Optional[str]]
      recipe_name: Mapped[str]
      recipe_image_url: Mapped[Optional[str]]
      availability_pct: Mapped[Optional[float]]  # pre-computed
      synced_at: Mapped[datetime] = mapped_column(default=func.now())
  ```

- [ ] Alembic migration for all three tables
- [ ] Indexes on `mealie_food_id`, `product_master_id`, `plan_date`

### 1.4 Ingredient Matching Service

**File:** `services/ingredient_matching.py`

- [ ] `match_mealie_food_to_inventory(mealie_food) → list[InventoryItem]`
  - [ ] Check `ingredient_map` for existing mapping
  - [ ] If mapped, query `inventory_item` for in-stock items of that product
  - [ ] Return matched items with available quantities
  
- [ ] `auto_map_food(mealie_food_name) → Optional[ProductMaster]`
  - [ ] Exact match against `product_master.canonical_name`
  - [ ] Fuzzy match using RapidFuzz (threshold ≥ 80)
  - [ ] Token overlap match (e.g., "chicken breast" matches "Atria Kanan Rintafilee")
  - [ ] LLM fallback: ask Ollama "Is [mealie_food] the same as [product_name]?"
  - [ ] Return best match with confidence score

- [ ] `compute_recipe_availability(recipe) → RecipeAvailability`
  ```python
  @dataclass
  class IngredientAvailability:
      mealie_food_name: str
      required_quantity: float
      required_unit: str
      available_quantity: float
      available_unit: str
      status: str  # "available" | "partial" | "missing" | "unmapped"
      matched_inventory_items: list[InventoryItem]

  @dataclass
  class RecipeAvailability:
      recipe_id: UUID
      recipe_name: str
      total_ingredients: int
      available_count: int
      partial_count: int
      missing_count: int
      unmapped_count: int
      availability_pct: float  # 0.0 to 1.0
      ingredients: list[IngredientAvailability]
      can_cook: bool  # True if availability_pct >= threshold
  ```

- [ ] `rank_recipes_by_availability(recipes) → list[RecipeAvailability]`
  - [ ] Compute availability for each recipe
  - [ ] Sort by availability_pct descending

- [ ] `rank_recipes_by_expiry_coverage(recipes, expiring_items) → list`
  - [ ] Score recipes by how many expiring items they use
  - [ ] Weight by days-to-expiry (more urgent = higher weight)
  - [ ] Sort by expiry coverage score descending

- [ ] `calculate_deductions(recipe, servings) → list[InventoryDeduction]`
  - [ ] For each mapped ingredient, calculate quantity to deduct
  - [ ] Handle unit conversion (e.g., recipe says "2 cups milk", inventory tracks ml)
  - [ ] Prefer items expiring sooner (FIFO by expiry)
  - [ ] Return list of (inventory_item_id, quantity_to_deduct)

### 1.5 Unit Conversion Helpers

**File:** `services/unit_conversion.py`

- [ ] Basic volume conversions (ml, l, dl, cup, tbsp, tsp)
- [ ] Basic weight conversions (g, kg, oz, lb)
- [ ] Count passthrough (pcs, kpl)
- [ ] `convert(quantity, from_unit, to_unit) → float`
- [ ] `are_compatible(unit_a, unit_b) → bool`
- [ ] Finnish unit name support (e.g., "rkl" = tablespoon, "tl" = teaspoon, "dl" = deciliter)

---

## Phase 2: Recipe API & Frontend

**Goal:** Browse recipes, see availability, cook and deduct  
**Prerequisites:** Phase 1 complete, ingredient mapping populated  
**Estimated Duration:** 2 weeks

### 2.1 Recipe API Endpoints

**File:** `api/routes/recipes.py`

- [ ] `GET /api/recipes`
  - [ ] Proxies to Mealie with pagination
  - [ ] Enriches each recipe summary with `availability_pct`
  - [ ] Query params: `search`, `category`, `tag`, `min_availability`
  - [ ] Returns: list of recipe summaries + availability data

- [ ] `GET /api/recipes/{slug}`
  - [ ] Fetches full recipe from Mealie
  - [ ] Computes per-ingredient availability
  - [ ] Returns: full recipe + ingredient availability details

- [ ] `GET /api/recipes/cookable`
  - [ ] Returns recipes where availability ≥ configurable threshold (default 80%)
  - [ ] Sorted by availability descending
  - [ ] Limit param for "top N" results

- [ ] `GET /api/recipes/suggestions`
  - [ ] Query param: `strategy` = `expiring` | `popular` | `random`
  - [ ] `expiring`: recipes that use items expiring within N days
  - [ ] `popular`: recipes most frequently cooked (from cooking_session)
  - [ ] `random`: random selection from cookable recipes
  - [ ] Returns: ranked list with reasoning

- [ ] `POST /api/recipes/{slug}/cook`
  - [ ] Body: `{ servings: float, context: str }`
  - [ ] Deducts ingredients from inventory
  - [ ] Creates `CookingSession` record
  - [ ] Creates `ConsumptionLog` entries for each deducted item
  - [ ] Broadcasts inventory update via WebSocket
  - [ ] Returns: cooking session summary with what was deducted and what was missing

- [ ] `GET /api/recipes/history`
  - [ ] Returns recent cooking sessions
  - [ ] Pagination support

- [ ] `POST /api/recipes/import`
  - [ ] Body: `{ url: string }` or `{ image: file }`
  - [ ] Proxies to Mealie's import functionality
  - [ ] Returns: created recipe summary

### 2.2 Ingredient Mapping Endpoints

- [ ] `GET /api/ingredient-map`
  - [ ] List all mappings with status (mapped, unmapped, low-confidence)
  - [ ] Filter: `unmapped_only`, `low_confidence`

- [ ] `POST /api/ingredient-map`
  - [ ] Body: `{ mealie_food_id, mealie_food_name, product_master_id }`
  - [ ] Creates manual mapping (manually_verified = true)

- [ ] `DELETE /api/ingredient-map/{id}`
  - [ ] Remove a mapping

- [ ] `POST /api/ingredient-map/auto-map`
  - [ ] Trigger auto-mapping for all unmapped Mealie foods
  - [ ] Queues as Celery task (can be slow for large food databases)
  - [ ] Returns: task ID for progress tracking

- [ ] `GET /api/ingredient-map/suggestions/{mealie_food_id}`
  - [ ] Returns top-N product_master candidates for a given Mealie food
  - [ ] Uses fuzzy + semantic matching

### 2.3 Meal Plan Endpoints

- [ ] `GET /api/meal-plan`
  - [ ] Query params: `start_date`, `end_date` (default: current week)
  - [ ] Returns cached meal plan entries with availability data

- [ ] `POST /api/meal-plan`
  - [ ] Body: `{ date, entry_type, recipe_slug }`
  - [ ] Creates entry in Mealie, updates local cache

- [ ] `DELETE /api/meal-plan/{id}`
  - [ ] Removes from Mealie, updates local cache

- [ ] `GET /api/meal-plan/shopping-needs`
  - [ ] For the current week's meal plan
  - [ ] Computes all ingredients needed minus current inventory
  - [ ] Groups by category for shopping convenience

### 2.4 Pydantic Request/Response Schemas

**File:** `api/schemas/recipes.py`

- [ ] `RecipeSummaryResponse` — recipe card data + availability_pct
- [ ] `RecipeDetailResponse` — full recipe + per-ingredient availability
- [ ] `RecipeAvailabilityResponse` — availability breakdown
- [ ] `CookRecipeRequest` — servings, context
- [ ] `CookRecipeResponse` — deductions made, items missing
- [ ] `CookingSessionResponse` — history entry
- [ ] `IngredientMapCreate` — manual mapping input
- [ ] `IngredientMapResponse` — mapping with product details
- [ ] `MealPlanEntryResponse` — plan entry with availability
- [ ] `ShoppingNeedsResponse` — categorized shopping list

### 2.5 Frontend — Recipe Browser

- [ ] **RecipeCard** (`components/recipes/RecipeCard.tsx`)
  - [ ] Recipe image thumbnail (proxied from Mealie)
  - [ ] Recipe name and description
  - [ ] Prep/cook time display
  - [ ] AvailabilityBadge showing % of ingredients available
  - [ ] Tap to open detail
  - [ ] Touch-friendly sizing (min 44px targets)

- [ ] **AvailabilityBadge** (`components/recipes/AvailabilityBadge.tsx`)
  - [ ] Circular or pill badge showing percentage
  - [ ] Color coding:
    - 🟢 ≥ 80% — "Ready to cook"
    - 🟡 50-79% — "Almost there"
    - 🔴 < 50% — "Missing ingredients"
  - [ ] Tap to see breakdown

- [ ] **RecipeDetail** (`components/recipes/RecipeDetail.tsx`)
  - [ ] Full recipe display (image, description, times)
  - [ ] Ingredient list with per-item availability
  - [ ] Instructions (step-by-step)
  - [ ] Servings adjuster (increment/decrement)
  - [ ] "Cook This" button (prominent)
  - [ ] Link to original source (if URL import)

- [ ] **IngredientList** (`components/recipes/IngredientList.tsx`)
  - [ ] Each ingredient row shows:
    - [ ] Food name + quantity + unit
    - [ ] Status icon: ✅ available, ⚠️ partial, ❌ missing, ❓ unmapped
    - [ ] If partial: "have X, need Y"
    - [ ] If unmapped: "Map ingredient" link
  - [ ] Color-coded background per status

- [ ] **CookButton** (`components/recipes/CookButton.tsx`)
  - [ ] Large touch target
  - [ ] Shows ingredient summary ("12/15 ingredients ready")
  - [ ] Confirmation dialog before deducting
  - [ ] Cooking animation/feedback on success
  - [ ] Error state if deduction fails

- [ ] **RecipeFilter** (`components/recipes/RecipeFilter.tsx`)
  - [ ] Search input with debounce
  - [ ] Category filter pills (horizontal scroll)
  - [ ] Availability filter: "Ready to cook", "Almost ready", "All"
  - [ ] Sort: "Best match", "Expiring coverage", "Recently cooked", "Rating"

- [ ] **SuggestionPanel** (`components/recipes/SuggestionPanel.tsx`)
  - [ ] "Use expiring items" section at top of recipe browser
  - [ ] Shows 2-3 recipe cards that use items expiring soon
  - [ ] Highlights which expiring items each recipe uses
  - [ ] Collapsible/dismissible

### 2.6 Frontend — Recipe Pages

- [ ] **Recipe browser page** (`app/recipes/page.tsx`)
  - [ ] Grid of RecipeCards
  - [ ] SuggestionPanel at top
  - [ ] RecipeFilter bar
  - [ ] Infinite scroll or pagination
  - [ ] Loading skeletons

- [ ] **Recipe detail page** (`app/recipes/[id]/page.tsx`)
  - [ ] RecipeDetail view
  - [ ] IngredientList with availability
  - [ ] CookButton
  - [ ] Related recipes (same category)

### 2.7 Frontend — State & Hooks

- [ ] **useRecipes** (`hooks/useRecipes.ts`)
  - [ ] React Query for recipe list with filters
  - [ ] Search with debounce
  - [ ] Cook mutation
  - [ ] Optimistic inventory updates on cook

- [ ] **useMealPlan** (`hooks/useMealPlan.ts`)
  - [ ] React Query for weekly meal plan
  - [ ] Add/remove mutations

- [ ] **Recipe types** (`types/recipe.ts`)
  - [ ] TypeScript interfaces matching backend schemas

### 2.8 Navigation Integration

- [ ] Add "Recipes" entry to main sidebar/navigation
- [ ] Add recipe suggestion count badge to nav (e.g., "3 recipes for expiring items")
- [ ] "Cook mode" context in ContextSelector (existing component)
- [ ] Integration with existing ExpiringPanel — "Recipes using these items" link

---

## Phase 3: Meal Planning & Shopping Bridge

**Goal:** Weekly meal planning, smart shopping lists  
**Prerequisites:** Phase 2 complete, regular recipe usage  
**Estimated Duration:** 2 weeks

### 3.1 Meal Plan Frontend

- [ ] **MealPlanWeek** (`components/recipes/MealPlanWeek.tsx`)
  - [ ] 7-day grid layout (landscape iPad)
  - [ ] Rows: Breakfast, Lunch, Dinner
  - [ ] Recipe cards in each cell
  - [ ] Drag-and-drop to rearrange (touch-friendly)
  - [ ] "Add recipe" button per cell
  - [ ] Availability indicator per day
  - [ ] Touch-friendly week navigation (prev/next)

- [ ] **Meal plan page** (`app/recipes/meal-plan/page.tsx`)
  - [ ] MealPlanWeek component
  - [ ] Weekly shopping needs summary
  - [ ] "Auto-fill week" button (random from cookable)
  - [ ] Sync status indicator

### 3.2 Shopping List Bridge

- [ ] `POST /api/meal-plan/generate-shopping-list`
  - [ ] Calculates all ingredients needed for selected date range
  - [ ] Subtracts current inventory
  - [ ] Groups by category (matching grocery store sections)
  - [ ] Optionally pushes to Mealie shopping list

- [ ] Integration with Fridge Logger Phase 3 shopping lists
  - [ ] Merge meal plan needs with low-stock alerts
  - [ ] Deduplicate items across multiple recipes

### 3.3 Meal Plan Sync

- [ ] Celery beat task: sync meal plan from Mealie every 15 minutes
- [ ] Pre-compute availability for each planned recipe
- [ ] WebSocket notification when meal plan changes
- [ ] Handle conflicts (changes in both Mealie UI and Fridge Logger)

### 3.4 Cooking Session Analytics

- [ ] `GET /api/recipes/stats`
  - [ ] Most cooked recipes (all time, this month)
  - [ ] Cooking frequency by context (breakfast/lunch/dinner)
  - [ ] Average ingredient availability when cooking
  - [ ] Most commonly missing ingredients

---

## Phase 4: HowToCook Import Pipeline

**Goal:** Translate and import Chinese recipe collection  
**Prerequisites:** Phase 1 Mealie client working  
**Estimated Duration:** 1 week (batch job, mostly automated)

### 4.1 Translation Pipeline

- [ ] **Clone/download script** — fetch HowToCook repo markdown files
- [ ] **Recipe file parser** — extract structured sections from markdown
  - [ ] Ingredients list (Chinese, with precise measurements)
  - [ ] Steps (numbered)
  - [ ] Tips/notes
  - [ ] Metadata (category from directory path)
- [ ] **LLM translation task** (`tasks/mealie_tasks.py`)
  ```python
  TRANSLATION_PROMPT = """
  Translate this Chinese recipe to English. Preserve the structure exactly.
  
  For ingredients:
  - Translate ingredient names to English
  - Convert Chinese measurements to metric (克→g, 毫升→ml, 勺→tbsp, 茶匙→tsp)
  - Keep quantities as numbers
  
  For steps:
  - Translate to clear English instructions
  - Preserve step numbering
  
  For ingredient names that are specifically Chinese (e.g., 豆瓣酱, 花椒),
  provide the pinyin romanization in parentheses: "doubanjiang (豆瓣酱)"
  
  Respond in this JSON format:
  {
    "name": "...",
    "description": "...",
    "ingredients": [{"quantity": ..., "unit": "...", "food": "..."}],
    "instructions": [{"text": "..."}],
    "tags": ["chinese", "..."],
    "prep_time": "...",
    "cook_time": "..."
  }
  
  Recipe markdown:
  {recipe_markdown}
  """
  ```
- [ ] **Mealie import task** — push translated recipe via Mealie API
- [ ] **Batch orchestrator** — iterate all markdown files, translate, import
  - [ ] Progress tracking (X of Y completed)
  - [ ] Error handling (skip failures, log for review)
  - [ ] Rate limiting (don't overwhelm Ollama)
  - [ ] Idempotency (check if recipe already exists by name)
- [ ] **Category mapping** — map HowToCook directories to Mealie categories
  ```python
  CATEGORY_MAP = {
      "vegetable_dish": "Vegetables",
      "meat_dish": "Meat",
      "staple": "Staples",
      "soup": "Soups",
      "dessert": "Desserts",
      "drink": "Beverages",
      "condiment": "Condiments",
      "breakfast": "Breakfast",
  }
  ```
- [ ] **Post-import tagging** — tag all imported recipes with "howtocook", "chinese"
- [ ] **Quality review tool** — simple script to review translations and flag issues

### 4.2 Ingredient Availability Check

- [ ] After import, flag recipes with ingredients unavailable in Finland
- [ ] Tag with "specialty-ingredients" if > 30% of ingredients are unusual
- [ ] Generate a "specialty shopping list" for these ingredients

---

## Phase 5: Home Assistant & Advanced Features

**Goal:** Voice control, notifications, smart suggestions  
**Prerequisites:** Phases 1-3 complete, Home Assistant running  
**Estimated Duration:** Ongoing

### 5.1 Home Assistant Integration via Mealie

- [ ] Configure Mealie HA integration (native, since HA 2024.7)
  - [ ] Expose meal plan as HA calendar
  - [ ] Expose shopping list as HA to-do list
  - [ ] Use HA automations for mealtime notifications
- [ ] Fridge Logger custom HA sensors
  - [ ] `sensor.recipes_cookable_count` — number of cookable recipes
  - [ ] `sensor.recipes_expiring_suggestion` — top suggestion name
  - [ ] `sensor.meal_plan_today` — today's planned meal

### 5.2 Notification Pipeline

- [ ] Morning notification: "Today's meal plan: [recipe]. You have all ingredients ✅"
- [ ] Expiry-driven: "3 items expiring tomorrow — here are recipes to use them"
- [ ] Post-shopping: when receipt scanned, suggest "You can now cook: [recipes]"

### 5.3 Voice Queries (via HA)

- [ ] "What can I cook tonight?" → top 3 cookable dinner recipes
- [ ] "Do I have ingredients for [recipe]?" → availability check
- [ ] "Add [recipe] to this week's meal plan" → create meal plan entry
- [ ] "What's for dinner?" → today's meal plan entry

### 5.4 Smart Substitution Suggestions

- [ ] When recipe is 85-95% available, suggest substitutions for missing items
- [ ] Use Ollama: "Can I substitute [missing] with [available] in [recipe]?"
- [ ] Learn from user confirmations

---

## Celery Task Summary

### Scheduled Tasks (celery-beat)

| Task | Schedule | Description |
|------|----------|-------------|
| `sync_meal_plan` | Every 15 min | Fetch Mealie meal plan, update cache |
| `precompute_availability` | Every 30 min | Recompute availability for cached recipes |
| `auto_map_new_foods` | Daily at 03:00 | Map any new Mealie foods to products |
| `sync_cooking_stats` | Daily at 04:00 | Aggregate cooking session analytics |

### On-Demand Tasks

| Task | Trigger | Description |
|------|---------|-------------|
| `import_howtocook_batch` | Manual/API | Full HowToCook translation pipeline |
| `translate_single_recipe` | Called by batch | Translate one markdown → Mealie recipe |
| `auto_map_food` | New food discovered | Fuzzy match + LLM identification |
| `compute_recipe_availability` | Recipe viewed | Real-time availability calculation |

---

## Testing Strategy

### Unit Tests
- [ ] Mealie client methods (mock httpx responses)
- [ ] Ingredient matching algorithms (fuzzy, exact, LLM)
- [ ] Unit conversion logic
- [ ] Availability computation
- [ ] Deduction calculation
- [ ] Translation prompt parsing

### Integration Tests
- [ ] Full cook flow: fetch recipe → compute availability → deduct → log
- [ ] Mealie client against real Mealie instance (docker test environment)
- [ ] Auto-mapping pipeline with sample Finnish products
- [ ] Meal plan sync round-trip

### Test Data
- [ ] Sample Mealie recipes with Finnish-relevant ingredients
- [ ] Product master entries for common Finnish grocery items
- [ ] Pre-built ingredient mappings for testing
- [ ] Sample HowToCook markdown files for translation testing

---

## Configuration Reference

### Environment Variables

```env
# Mealie Connection
MEALIE_URL=http://mealie:9000
MEALIE_API_TOKEN=ey...
MEALIE_ENABLED=true

# Caching
MEALIE_CACHE_TTL_RECIPES=300
MEALIE_CACHE_TTL_FOODS=3600

# Matching
INGREDIENT_MATCH_THRESHOLD=80
INGREDIENT_AUTO_ACCEPT_CONFIDENCE=0.95
INGREDIENT_SUGGEST_CONFIDENCE=0.70

# Recipe Suggestions
RECIPE_COOKABLE_THRESHOLD=0.80
RECIPE_EXPIRY_LOOKAHEAD_DAYS=3
RECIPE_SUGGESTION_COUNT=5

# HowToCook Import
HOWTOCOOK_REPO_PATH=/app/data/howtocook
HOWTOCOOK_TRANSLATE_MODEL=qwen2-vl:7b
HOWTOCOOK_BATCH_SIZE=10
HOWTOCOOK_RATE_LIMIT_SECONDS=5
```

### Dependencies (additions to requirements.txt)

```
# Already present in project:
# httpx, rapidfuzz, pydantic

# No new dependencies required — Mealie integration
# uses existing httpx client and matching libraries
```

---

## Risk Assessment & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Mealie API changes in minor version | Medium | Medium | Pin Mealie version, wrap all API calls in client |
| Ingredient mapping is labor-intensive initially | High | Medium | Auto-mapping with LLM, learn from corrections |
| Unit conversion inaccuracies | Medium | Low | Conservative defaults, manual override per recipe |
| Ollama too slow for batch translation | Medium | Low | Rate-limit, run overnight, cache results |
| Mealie goes down | Low | Medium | Graceful degradation, cached data, clear UI feedback |
| Recipe ingredient names too different from receipt names | High | Medium | Multi-layer matching (fuzzy + LLM + manual) |

---

## Decision Log

### Decision: Mealie over Tandoor
**Rationale:** Mealie's API-first design, structured ingredient model (foods/units), native Ollama support, and Home Assistant integration make it the strongest fit for a headless recipe backend. Tandoor is more feature-rich as a standalone app but heavier to deploy and less API-ergonomic for our use case. Since Fridge Logger is the primary UI, Mealie's UI quality is irrelevant — we need its database and parsing capabilities.

### Decision: External Mealie instance, not embedded recipes
**Rationale:** Building a recipe system from scratch would add months of work for an inferior result. Mealie provides URL scraping, structured ingredient parsing, meal planning, image support, and community-maintained recipe import — all via API. Fridge Logger focuses on what it does best: inventory tracking and the inventory↔recipe bridge.

### Decision: One-directional food mapping (Mealie → Fridge Logger)
**Rationale:** Mealie's food database is recipe-oriented ("chicken breast", "flour", "butter") while Fridge Logger's product_master is store-oriented ("Atria Kanan Rintafilee 400g"). These are fundamentally different abstractions. A thin mapping table bridges them without trying to force synchronization. Fridge Logger is the source of truth for "what's in the fridge," Mealie for "what goes in a recipe."

### Decision: HowToCook as optional seed data, not core feature
**Rationale:** The Chinese recipe collection is interesting and high-quality, but most recipes use ingredients not commonly found in Finnish stores. It's better as a fun batch import project after the core integration is working, not a dependency for the recipe feature to be useful.

---

## Reference Links

- [Mealie Documentation](https://docs.mealie.io/)
- [Mealie API Usage Guide](https://docs.mealie.io/documentation/getting-started/api-usage/)
- [Mealie OpenAI/Ollama Config](https://docs.mealie.io/documentation/getting-started/installation/open-ai/)
- [Mealie Home Assistant Integration](https://www.home-assistant.io/integrations/mealie/)
- [Mealie GitHub Repository](https://github.com/mealie-recipes/mealie)
- [HowToCook Repository](https://github.com/Anduin2017/HowToCook)
- [Fridge Logger Architecture](./ARCHITECTURE.md)
- [Fridge Logger Backend TODO](./backend_TODO.md)
- [Fridge Logger Frontend TODO](./frontend_TODO.md)
