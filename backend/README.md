# Kyokki Backend

FastAPI backend for Kyokki refrigerator inventory system.

## Development Workflow

### Database Migrations

**IMPORTANT: Always use Docker for database operations**

The backend can run locally for development, but PostgreSQL runs in Docker. All database migrations **must** be run through Docker to access the database.

```bash
# Create a new migration
docker compose run --rm kyokki-api alembic revision --autogenerate -m "Description"

# Apply migrations
docker compose run --rm kyokki-api alembic upgrade head

# Check current migration status
docker compose run --rm kyokki-api alembic current

# View migration history
docker compose run --rm kyokki-api alembic history

# Rollback one migration
docker compose run --rm kyokki-api alembic downgrade -1
```

**Why Docker?**
- PostgreSQL hostname `postgres` only resolves inside Docker network
- Running locally would fail with "could not translate host name" error
- `docker compose run` creates temporary container with same config as backend service

### Running the Backend

#### Option 1: Local Development (Recommended for Hot Reload)
```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Run with auto-reload
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Option 2: Full Docker
```bash
docker compose up kyokki-api
```

### Testing

```bash
# Run all tests
cd backend && pytest

# Run with coverage
cd backend && pytest --cov=app --cov-report=html

# Run specific test file
cd backend && pytest tests/api/test_health.py -v
```

### Code Quality

```bash
# Lint
ruff check backend/

# Format
ruff format backend/

# Type checking
mypy backend/app/
```

## Project Structure

```
backend/
├── alembic/              # Database migrations
│   ├── versions/         # Migration files
│   └── env.py            # Alembic configuration
├── app/
│   ├── api/              # API routes
│   ├── core/             # Core configuration
│   ├── crud/             # Database operations
│   ├── db/               # Database setup
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   └── main.py           # FastAPI application
└── tests/                # Test suite
```

## Database Schema

See `docs/ARCHITECTURE.md` for complete database design and relationships.

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Database
POSTGRES_SERVER=postgres  # Docker hostname
POSTGRES_DB=kyokki
POSTGRES_USER=kyokki_user
POSTGRES_PASSWORD=your_password

# External Services
MINERU_BASE_URL=http://192.168.0.136:8000
LLM_BASE_URL=http://192.168.0.247:9003/v1
LLM_MODEL=qwen2-vl
```

## Common Issues

### "could not translate host name 'postgres'"
**Solution:** Use Docker for the command:
```bash
docker compose run --rm kyokki-api <command>
```

### Import errors in migrations
**Solution:** Alembic env.py adds backend dir to path automatically. Imports should use `from app.models import ...`

### "No module named 'psycopg2'"
**Solution:** Already in requirements.txt. Reinstall dependencies:
```bash
pip install -r requirements.txt
```
