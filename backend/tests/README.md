# Kyokki Backend Tests

## Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── README.md               # This file
├── api/                    # API endpoint tests
│   ├── __init__.py
│   └── test_health.py      # Health check tests
├── services/               # Service layer tests
│   └── __init__.py
└── integration/            # Integration tests
    ├── __init__.py
    └── test_connections.py # External service tests
```

## Running Tests

### All tests
```bash
pytest
```

### Specific test file
```bash
pytest tests/api/test_health.py
```

### Specific test class
```bash
pytest tests/api/test_health.py::TestHealthEndpoint
```

### Specific test function
```bash
pytest tests/api/test_health.py::TestHealthEndpoint::test_health_check_returns_200
```

### By marker
```bash
# Run only unit tests (fast)
pytest -m unit

# Run only integration tests
pytest -m integration

# Run tests that require database
pytest -m requires_db

# Skip integration tests
pytest -m "not integration"
```

### With coverage
```bash
# Run with coverage report
pytest --cov=app --cov-report=html

# View coverage report
open htmlcov/index.html  # or start htmlcov/index.html on Windows
```

### Verbose output
```bash
pytest -v                  # Verbose
pytest -vv                 # Very verbose
pytest -s                  # Show print statements
```

## Test Markers

- `unit`: Fast, isolated unit tests (no external dependencies)
- `integration`: Tests that require external services
- `slow`: Tests that may take >1 second
- `requires_db`: Requires PostgreSQL connection
- `requires_redis`: Requires Redis connection
- `requires_mineru`: Requires MinerU OCR service
- `requires_ollama`: Requires Ollama LLM service

## Writing Tests

### API Tests (Unit)
```python
import pytest
from httpx import AsyncClient

class TestMyEndpoint:
    async def test_endpoint_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/my-endpoint")
        assert response.status_code == 200
```

### Integration Tests
```python
import pytest

@pytest.mark.integration
@pytest.mark.requires_db
class TestDatabase:
    async def test_query(self, db_session) -> None:
        # Test database operations
        pass
```

### Service Tests
```python
import pytest

@pytest.mark.unit
class TestMyService:
    def test_service_logic(self) -> None:
        # Test service logic without external dependencies
        pass
```

## Fixtures

Available in `conftest.py`:

- `client`: Async HTTP client for API testing
- `sample_receipt_data`: Mock receipt data
- `sample_product`: Mock product data

## Configuration

See `pytest.ini` for pytest configuration options.

## CI/CD

In CI pipelines, run:
```bash
# Fast tests only (skip integration)
pytest -m "not integration"

# All tests (if services available)
pytest
```

## Best Practices

1. **Organize by layer**: API tests in `api/`, service tests in `services/`, etc.
2. **Use markers**: Mark integration tests appropriately
3. **Keep tests fast**: Mock external services in unit tests
4. **Use fixtures**: Share common setup via fixtures
5. **Descriptive names**: Test names should describe what they test
6. **Arrange-Act-Assert**: Structure tests clearly
7. **One assertion per test**: Keep tests focused
