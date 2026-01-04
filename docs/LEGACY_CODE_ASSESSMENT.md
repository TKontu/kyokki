# Legacy Code Assessment

## Summary

The legacy code contains a FastAPI + Celery + PostgreSQL + Redis stack for a food product tracking system. Much of the infrastructure code is well-written and reusable with minimal changes (**~40% of legacy code can be reused**).

---

## default.yaml Configuration

The `default.yaml` file is from a document processing/RAG system and contains useful configuration for services we'll use:

### ✅ Directly Relevant Configurations:
- **MinerU OCR**: Already configured at `http://192.168.0.136:8000`
  - API type: selfhosted
  - Model: pipeline (faster, 2-10s per document)
  - Settings: tables enabled, formulas disabled
- **Ollama LLM**: Configured at `http://192.168.0.247:9003/v1`
  - We need Qwen2-VL model for receipt/image analysis
- **Redis**: Host configuration (redis:6379)
- **PostgreSQL**: Connection string pattern
- **Celery**: Task timeout and worker settings

### 📝 Action Items:
1. Create new `config.yaml` or `.env` for Kyokki based on relevant settings
2. Ensure MinerU is accessible at the configured endpoint
3. Install Qwen2-VL model in Ollama for receipt analysis
4. Adapt database connection settings for our schema

---

## Legacy Code Reusability Analysis

### ✅ REUSE AS-IS or MINIMAL CHANGES (< 30% refactoring)

#### 1. **app/core/config.py** (5% refactoring)
- **Status**: Excellent foundation
- **What it does**: Pydantic settings with env vars
- **Changes needed**:
  - Add `MINERU_BASE_URL`, `MINERU_TIMEOUT`
  - Remove `OLLAMA_HOST`, use OpenAI-compatible endpoint instead
  - Add any additional config fields from docs/ARCHITECTURE.md
- **Verdict**: ✅ REUSE

#### 2. **app/db/session.py** (0% refactoring)
- **Status**: Perfect
- **What it does**: AsyncPG engine and session setup
- **Changes needed**: None
- **Verdict**: ✅ REUSE AS-IS

#### 3. **app/core/celery_app.py** (10% refactoring)
- **Status**: Clean and simple
- **What it does**: Basic Celery app configuration
- **Changes needed**: Update task imports, add task routing if needed
- **Verdict**: ✅ REUSE

#### 4. **app/core/logging.py** (5% refactoring)
- **Status**: Excellent structured logging
- **What it does**: JSON logging, performance decorator, rotating file handlers
- **Changes needed**: Update log paths, add DEBUG flag to config
- **Verdict**: ✅ REUSE

#### 5. **app/services/websockets.py** (0% refactoring)
- **Status**: Simple and effective
- **What it does**: WebSocket connection manager
- **Changes needed**: None
- **Verdict**: ✅ REUSE AS-IS

#### 6. **app/api/endpoints/health.py** (0% refactoring)
- **Status**: Basic health check
- **What it does**: Returns {"status": "ok"}
- **Changes needed**: Could enhance with DB/Redis checks later
- **Verdict**: ✅ REUSE AS-IS

#### 7. **app/crud/base.py** (0% refactoring)
- **Status**: Generic CRUD operations
- **What it does**: Base class for async CRUD operations
- **Changes needed**: None
- **Verdict**: ✅ REUSE AS-IS

#### 8. **app/main.py** (20% refactoring)
- **Status**: Good structure
- **What it does**: FastAPI app with lifespan, CORS, middleware, Redis listener
- **Changes needed**:
  - Update router imports
  - Adjust CORS origins
  - Update Redis channel names
  - Remove LoggingMiddleware if not needed (or keep it)
- **Verdict**: ✅ REUSE with minor updates

#### 9. **docker-compose.yml** (25% refactoring)
- **Status**: Good foundation
- **What it does**: Services: nginx, api, celery-worker, postgres, redis, frontend
- **Changes needed**:
  - Replace nginx with Traefik (per architecture docs)
  - Update service names
  - Add MinerU service references (if running locally)
  - Update volumes and networks
- **Verdict**: ✅ REUSE as template

---

### ⚠️ PARTIALLY REUSABLE (30-50% refactoring)

#### 10. **app/services/image_processing.py** (40% refactoring)
- **Status**: Well-written but different use case
- **What it does**: Image preprocessing (EXIF correction, enhancement, resize, thumbnails)
- **Current approach**: Processes images before analysis
- **Our approach**: MinerU handles raw images directly
- **Potential use**:
  - Thumbnail generation for frontend display
  - Image optimization for upload/storage
  - NOT for OCR preprocessing (MinerU does this internally)
- **Verdict**: ⚠️ REUSE selectively (thumbnail generation only)

#### 11. **app/services/ollama.py** (45% refactoring)
- **Status**: Basic structure OK, needs significant updates
- **What it does**: Calls Ollama vision model for single product image analysis
- **Changes needed**:
  - Update for receipt parsing (not single product)
  - New prompt engineering for Finnish receipts
  - Use as fallback only (after MinerU + fuzzy match fails)
  - Better error handling
  - Make model configurable
- **Verdict**: ⚠️ REUSE as template, significant prompt updates

#### 12. **app/tasks.py** (50% refactoring)
- **Status**: Pattern is useful but completely different workflow
- **What it does**: Celery task for single image → Ollama → save item
- **Our workflow**: Receipt upload → MinerU OCR → parse lines → fuzzy match → save batch
- **Useful patterns**:
  - Async task execution
  - Redis pub/sub for updates
  - Database session handling in tasks
- **Verdict**: ⚠️ REUSE pattern, rewrite logic

---

### ❌ CREATE FROM SCRATCH (> 50% refactoring)

#### 13. **app/models/product.py** (80% refactoring)
- **Status**: Schema doesn't match our design
- **Legacy schema**: Single `products` table with keywords, confidence_threshold
- **Our schema**: `product_master` + `store_product_alias` + `inventory_item` + `consumption_log`
- **Verdict**: ❌ CREATE FROM SCRATCH using docs/ARCHITECTURE.md schema

#### 14. **requirements.txt** (60% refactoring)
- **Status**: Missing many dependencies, has unnecessary ones
- **Missing**: pdfplumber, rapidfuzz, httpx, alembic, open-food-facts, structlog
- **Unnecessary**: opencv-python-headless, ollama (use httpx instead)
- **Verdict**: ❌ CREATE FROM SCRATCH

#### 15. **app/models/item.py** (Not reviewed, but likely 70%+ refactoring)
- Our `inventory_item` schema is significantly different
- **Verdict**: ❌ CREATE FROM SCRATCH

---

## Frontend Assessment

The legacy frontend is a Next.js app with:
- TypeScript
- Tailwind CSS
- Image upload component
- WebSocket integration
- Item list display

**Analysis**: The frontend structure is modern (Next.js 14 App Router) and could be reused, but the UI is for single-item scanning, not receipt processing. The wireframes in docs/ show a very different iPad-optimized interface.

**Verdict**: ⚠️ REUSE project structure and config, CREATE NEW components (50% refactoring)

---

## Recommended Reuse Strategy

### Phase 1: Infrastructure (Sprint 1)
1. ✅ Copy and adapt:
   - `app/core/config.py`
   - `app/core/logging.py`
   - `app/core/celery_app.py`
   - `app/db/session.py`
   - `app/crud/base.py`
   - `docker-compose.yml` (as template)

2. ✅ Copy as-is:
   - `app/services/websockets.py`
   - `app/api/endpoints/health.py`

### Phase 2: Database & Models (Sprint 1-2)
1. ❌ Create from scratch:
   - All models from docs/ARCHITECTURE.md schema
   - Alembic migrations
   - New requirements.txt

### Phase 3: Services (Sprint 2-3)
1. ⚠️ Adapt patterns from:
   - `app/tasks.py` (Celery pattern, Redis pub/sub)
   - `app/services/ollama.py` (as fallback service)

2. ❌ Create new:
   - MinerU integration service
   - Receipt parser service (store-specific parsers)
   - Fuzzy matching service
   - Open Food Facts integration

### Phase 4: API & Frontend (Sprint 3-4)
1. ✅ Adapt:
   - `app/main.py` (FastAPI structure)

2. ❌ Create new:
   - All API endpoints per docs/ARCHITECTURE.md
   - Frontend components per wireframes

---

## Files to Copy Immediately

```bash
# Create backend structure
mkdir -p backend/app/core
mkdir -p backend/app/db
mkdir -p backend/app/crud
mkdir -p backend/app/services
mkdir -p backend/app/api/endpoints

# Copy reusable files
cp legacy/backend/app/core/config.py backend/app/core/
cp legacy/backend/app/core/logging.py backend/app/core/
cp legacy/backend/app/core/celery_app.py backend/app/core/
cp legacy/backend/app/db/session.py backend/app/db/
cp legacy/backend/app/crud/base.py backend/app/crud/
cp legacy/backend/app/services/websockets.py backend/app/services/
cp legacy/backend/app/api/endpoints/health.py backend/app/api/endpoints/

# Copy as templates (will need updates)
cp legacy/backend/app/main.py backend/app/
cp legacy/docker-compose.yml docker-compose.yml
```

---

## Summary Statistics

| Category | Files | Refactoring | Decision |
|----------|-------|-------------|----------|
| Infrastructure | 7 files | 0-20% | ✅ Reuse |
| Patterns | 3 files | 40-50% | ⚠️ Adapt |
| Business Logic | 5+ files | 60-80% | ❌ Recreate |

**Total Reusable Code**: ~40% of infrastructure
**Total New Code Required**: ~60% (models, services, API endpoints, frontend components)

This is a significant head start on Sprint 1 infrastructure tasks!
