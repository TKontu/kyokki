# Pipeline Review: Increment 1.7 — Main Page Integration

## Flow

```
page.tsx
  ├─ useProductList()
  │   └─ productsAPI.list() → GET /api/products → list_products() → crud.get_products() → DB
  └─ <InventoryList>
      └─ useInventoryList()
          └─ inventoryAPI.list() → GET /api/inventory → list_inventory() → crud.get_inventory_items() → DB
```

Both fetches fire in parallel on mount. `productNames` map is built from the products result and passed down to `InventoryList` to resolve UUIDs to display names.

---

## Critical (must fix)

None found in the Increment 1.7 code path.

---

## Important (should fix)

### 1. Product fetch error swallowed — user sees UUID names with no feedback
**`frontend/app/page.tsx:8-14`**

If `GET /api/products` fails, `useProductList()` returns `{ data: undefined, isError: true }`. The memo falls back to `{}` (via `?? []`), and `InventoryList` renders with truncated UUID product names. No error state is surfaced to the user. They see a functional-looking page but with meaningless product identifiers.

**Fix:** Check `isError` from `useProductList()` and render a non-blocking warning banner, or at minimum log the failure. The error does not need to block the inventory view since items are still usable.

```tsx
const { data: products, isError: productsError } = useProductList()
// …
{productsError && (
  <p className="text-sm text-yellow-600 px-6 pt-2">
    Could not load product names — showing item IDs.
  </p>
)}
```

---

### 2. Redis listener exits on error and is never restarted
**`backend/app/main.py:46-47, 64`**

`redis_listener` catches `Exception`, logs it, and exits. `asyncio.create_task()` does not restart it. If Redis drops after startup — or is unreachable at startup — the listener task ends silently. The rest of the API continues responding normally, but all inventory mutation broadcasts are lost. Real-time WebSocket updates stop working with no observable signal.

**Fix:** Add a retry/restart loop around the listener body:

```python
async def redis_listener(app: FastAPI):
    while True:
        try:
            # … current listener body …
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Redis listener crashed, restarting in 5s", exc_info=True)
            await asyncio.sleep(5)
```

---

### 3. `IntegrityError` FK detection by substring match
**`backend/app/api/endpoints/products.py:75`**

```python
if "category" in str(e.orig):
```

This relies on the PostgreSQL error message containing the word "category". It breaks silently when: PostgreSQL is configured with a non-English `lc_messages` locale, the constraint is renamed, or a different FK column coincidentally also contains "category" in its name. When it fails, the caller receives `"Database integrity error"` with no actionable detail.

**Fix:** Match against the constraint name directly using `e.orig.pgcode` and `e.orig.diag.constraint_name`:

```python
from psycopg2 import errorcodes
if e.orig.pgcode == errorcodes.FOREIGN_KEY_VIOLATION:
    raise HTTPException(status_code=400, detail=f"Category '{product.category}' does not exist") from e
```

---

## Minor

### 4. `sessionmaker` instead of `async_sessionmaker`
**`backend/app/db/session.py:9-11`**

```python
AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)
```

`sessionmaker` with `class_=AsyncSession` works at runtime but is the SQLAlchemy 1.x pattern. SQLAlchemy 2.x provides `async_sessionmaker` which has the correct type annotations and is the documented approach for async engines. No production failure, but will generate type checker warnings and may behave unexpectedly in edge cases (e.g., `expire_on_commit` default handling).

**Fix:** Replace with `async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`.

---

### 5. No loading state while product names resolve
**`frontend/app/page.tsx`**

`InventoryList` shows its own loading skeletons while `useInventoryList()` is pending, but there is no visual feedback that product names are still being fetched. In the common case where inventory resolves before products (inventory payload is larger but products are fetched first by mount order — race-dependent), items briefly show truncated UUIDs then snap to real names. Not a hard failure but visually jarring.

**Fix:** Either show a page-level skeleton until both queries resolve, or defer `productNames` resolution with a brief `isPending` check so items render only once both are ready. Given the 30s stale time in providers, this only affects cold loads.
