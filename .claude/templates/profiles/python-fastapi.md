# Profile: Python + FastAPI

Python 3.12+, FastAPI, Ruff, pytest, mypy, structlog.

## Project Commands

Paste into the `claude:commands` table in `CLAUDE.md`:

```
| install   | pip install -r requirements.txt -r requirements-dev.txt |
| test      | pytest |
| test-one  | pytest {arg} -v --tb=short |
| lint      | ruff check . |
| lint-fix  | ruff check . --fix |
| format    | ruff format . |
| typecheck | mypy src/ |
| run       | uvicorn app.main:app --reload |
| build     | n/a |
```

Using a virtualenv, prefix with the interpreter so the commands work without an activated shell —
`.venv/bin/python -m pytest`, `.venv/bin/ruff check .` (on Windows, `.venv\Scripts\`). Poetry or uv
projects substitute `poetry run` / `uv run`.

Setup, once:

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
pip install -e .               # editable install
```

## Toolchain config

```toml
# pyproject.toml
[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ASYNC"]
ignore = ["E501"]  # line length is handled by the formatter

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q"

[tool.mypy]
python_version = "3.12"
strict = true
ignore_missing_imports = true
```

## Code style

- PEP 8, enforced by Ruff. Max line length 88.
- Type hints required on every function signature.
- Explicit imports; never wildcards.

**Naming:** `snake_case` functions/variables/modules · `PascalCase` classes and type aliases ·
`SCREAMING_SNAKE_CASE` constants · `_leading_underscore` for internal use.

**Imports** — stdlib, third-party, local, separated by blank lines:

```python
import os
from pathlib import Path

import httpx
from pydantic import BaseModel

from app.core import config
from app.models import User
```

**Docstrings** — Google style:

```python
def process_data(items: list[str], limit: int = 10) -> dict[str, int]:
    """Process items and return frequency counts.

    Args:
        items: List of strings to process.
        limit: Maximum items to return.

    Returns:
        Dictionary mapping items to their counts.

    Raises:
        ValueError: If items is empty.
    """
```

**Type hints** — modern syntax (3.10+):

```python
def fetch(ids: list[int]) -> dict[str, Any] | None: ...

type UserMap = dict[str, list[User]]   # TypeAlias for complex types
```

## FastAPI patterns

**Router:**

```python
# app/api/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, service: UserService = Depends(get_user_service)) -> User:
    if not (user := await service.get(user_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
```

**Exception handler:**

```python
# app/main.py
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```

**Lifespan:**

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()      # startup
    yield
    await database.disconnect()   # shutdown

app = FastAPI(lifespan=lifespan)
```

**Dependency injection** — constructor injection, wired through `Depends`:

```python
class UserService:
    def __init__(self, db: Database, cache: Cache) -> None:
        self._db = db
        self._cache = cache

def get_user_service(db: Database = Depends(get_db)) -> UserService:
    return UserService(db)
```

**Configuration** — pydantic-settings, env vars, never hardcoded secrets. Precedence:
defaults < env vars < explicit args.

## Errors and logging

```python
class AppError(Exception):
    """Base exception for application errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)

class ValidationError(AppError): ...
class NotFoundError(AppError): ...
class AuthenticationError(AppError): ...
```

- Never a bare `except:` — catch specific exceptions.
- `raise ... from e` to preserve the chain.
- Convert external exceptions to domain exceptions at the boundary:

```python
import structlog

logger = structlog.get_logger(__name__)

try:
    result = external_api.call()
except httpx.HTTPError as e:
    logger.error("api_call_failed", url=e.request.url, status=e.response.status_code)
    raise ServiceUnavailableError("External service failed") from e
```

Structured logging — event name first, context as keyword fields:

```python
logger.info("user_created", user_id=user.id, email=user.email)
logger.error("payment_failed", order_id=order.id, reason=str(e))
```

Levels: `DEBUG` diagnostics · `INFO` operational events · `WARNING` unexpected but handled ·
`ERROR` needs attention · `CRITICAL` system-level failure.

## Feature gating

```python
from app.core.config import settings

if settings.feature_new_checkout_enabled:
    return new_checkout_flow(cart)
return legacy_checkout(cart)

def is_feature_enabled(user_id: str, rollout_pct: int) -> bool:
    return hash(user_id) % 100 < rollout_pct
```

## Testing

**Fixtures** (`tests/conftest.py`):

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest.fixture
def user_factory() -> Callable[..., User]:
    def _create(**overrides) -> User:
        defaults = {"name": "Test User", "email": "test@example.com"}
        return User(**(defaults | overrides))
    return _create
```

**Test layout** — one class per unit under test, one behaviour per test:

```python
# tests/test_users.py
class TestGetUser:
    async def test_returns_user_when_exists(self, client: AsyncClient) -> None:
        response = await client.get("/users/1")
        assert response.status_code == 200
        assert response.json()["id"] == 1

    async def test_returns_404_when_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/users/999")
        assert response.status_code == 404
```

## Debugging

- `breakpoint()` drops into pdb
- `pytest --pdb` — debug on failure
- `pytest -x` — stop at the first failure
- `pytest --lf` — rerun last failures
- `pytest -k "pattern"` — select by name

## Settings

Merge into `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": "ruff check --fix --quiet \"$CLAUDE_FILE_PATH\" || true" },
          { "type": "command", "command": "ruff format --quiet \"$CLAUDE_FILE_PATH\" || true" }
        ]
      }
    ]
  },
  "permissions": {
    "allow": [
      "Bash(pytest:*)",
      "Bash(python -m pytest:*)",
      "Bash(.venv/bin/pytest:*)",
      "Bash(.venv/bin/python -m pytest:*)",
      "Bash(ruff check:*)",
      "Bash(ruff format:*)",
      "Bash(.venv/bin/ruff:*)",
      "Bash(mypy:*)",
      "Bash(uvicorn:*)",
      "Bash(pip list:*)",
      "Bash(pip show:*)",
      "Bash(pip freeze:*)",
      "Bash(poetry show:*)",
      "Bash(poetry env info:*)",
      "Bash(uv pip list:*)",
      "Bash(uv pip show:*)",
      "Bash(alembic history:*)",
      "Bash(alembic current:*)",
      "Bash(alembic heads:*)"
    ]
  }
}
```
