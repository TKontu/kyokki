# CLAUDE.md - Python Project Guidelines

## Common Commands

```bash
# Environment setup
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .  # Editable install

# Testing
pytest                          # Run all tests
pytest tests/test_foo.py -v     # Single file, verbose
pytest -k "test_name"           # Run matching tests
pytest --cov=src --cov-report=html  # Coverage report

# Linting & Formatting
ruff check .                    # Lint
ruff check . --fix              # Lint + autofix
ruff format .                   # Format code
mypy src/                       # Type checking

# Running
python -m <package_name>        # Run as module
uvicorn app.main:app --reload   # FastAPI
flask run --debug               # Flask
```

## Code Style Conventions

### General Rules
- Follow PEP 8, enforced via Ruff
- Max line length: 88 characters (Black default)
- Use type hints for all function signatures
- Prefer explicit imports over wildcard imports

### Naming
- `snake_case`: functions, variables, modules
- `PascalCase`: classes, type aliases
- `SCREAMING_SNAKE_CASE`: constants
- `_private`: internal use (single underscore)

### Imports
Order: stdlib → third-party → local, separated by blank lines:
```python
import os
from pathlib import Path

import httpx
from pydantic import BaseModel

from app.core import config
from app.models import User
```

### Docstrings
Use Google-style docstrings:
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

### Type Hints
```python
# Use modern syntax (Python 3.10+)
def fetch(ids: list[int]) -> dict[str, Any] | None: ...

# For complex types, use TypeAlias
type UserMap = dict[str, list[User]]
```

## API & Content Design

### Response Format
```python
# Success response
{
    "data": { ... },
    "meta": {"page": 1, "total": 100}
}

# Error response
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human-readable message",
        "details": [{"field": "email", "issue": "Invalid format"}]
    }
}
```

### CLI Output
- Use `rich` for formatted terminal output
- Errors to stderr: `console.print("[red]Error:[/red] message", stderr=True)`
- Exit codes: 0 success, 1 general error, 2 usage error

## State Management

### Dependency Injection
Use constructor injection or FastAPI's `Depends`:
```python
class UserService:
    def __init__(self, db: Database, cache: Cache) -> None:
        self._db = db
        self._cache = cache

# FastAPI pattern
def get_user_service(db: Database = Depends(get_db)) -> UserService:
    return UserService(db)
```

### Configuration
- Use pydantic-settings for config with env vars
- Never hardcode secrets; use environment variables
- Config hierarchy: defaults < env vars < explicit args

## Logging

```python
import structlog

logger = structlog.get_logger(__name__)

# Structured logging with context
logger.info("user_created", user_id=user.id, email=user.email)
logger.error("payment_failed", order_id=order.id, reason=str(e))
```

### Log Levels
- `DEBUG`: Detailed diagnostic info
- `INFO`: General operational events
- `WARNING`: Unexpected but handled situations
- `ERROR`: Failures requiring attention
- `CRITICAL`: System-level failures

## Error Handling

### Exception Hierarchy
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

### Best Practices
- Never use bare `except:`; catch specific exceptions
- Use `raise ... from e` to preserve exception chains
- Log exceptions with context before re-raising
- Convert external exceptions to domain exceptions at boundaries

```python
try:
    result = external_api.call()
except httpx.HTTPError as e:
    logger.error("api_call_failed", url=e.request.url, status=e.response.status_code)
    raise ServiceUnavailableError("External service failed") from e
```

## Feature Gating

```python
from app.core.config import settings

# Environment-based flags
if settings.feature_new_checkout_enabled:
    return new_checkout_flow(cart)
return legacy_checkout(cart)

# Percentage rollout
def is_feature_enabled(user_id: str, rollout_pct: int) -> bool:
    return hash(user_id) % 100 < rollout_pct
```

## Debugging

```python
# Built-in debugger (Python 3.7+)
breakpoint()  # Drops into pdb

# Environment control
PYTHONBREAKPOINT=0 python app.py        # Disable breakpoints
PYTHONBREAKPOINT=ipdb.set_trace python  # Use ipdb instead

# Debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Common Debug Patterns
- Use `python -m pdb script.py` for post-mortem debugging
- `pytest --pdb` drops into debugger on failures
- `icecream` library for quick debug prints: `ic(variable)`

## Pull Request Template

```markdown
## Summary
Brief description of changes and motivation.

## Changes
- Added X to handle Y
- Refactored Z for clarity
- Fixed bug where A caused B

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Type hints added
- [ ] Docstrings updated
- [ ] No new linter warnings
- [ ] Breaking changes documented

## Related Issues
Closes #123
```
