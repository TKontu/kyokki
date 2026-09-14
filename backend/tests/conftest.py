"""Shared pytest fixtures for all tests."""

import os
from collections.abc import AsyncGenerator
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.db.session import engine as app_engine
from app.main import app
from app.models.category import Category
from app.models.product_master import ProductMaster
from app.services.broadcast_helpers import close_redis_client


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Create async HTTP client for testing FastAPI endpoints.

    Usage:
        async def test_endpoint(client):
            response = await client.get("/api/health")
            assert response.status_code == 200
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def sample_receipt_data() -> dict:
    """Sample receipt data for testing"""
    return {
        "store": "S-Market",
        "date": "2024-01-04",
        "items": [
            {"name": "Maito 1L", "price": 1.49, "quantity": 1},
            {"name": "Leipä 500g", "price": 2.29, "quantity": 2},
            {"name": "Juusto 200g", "price": 3.99, "quantity": 1},
        ],
        "total": 10.06,
    }


@pytest.fixture
def sample_product_data() -> dict:
    """Sample product data dict for testing (non-database)."""
    return {
        "name": "Maito",
        "category": "dairy",
        "default_shelf_life_days": 7,
        "opened_shelf_life_days": 3,
    }


@pytest.fixture
async def sample_category(db_session: AsyncSession) -> Category:
    """Return the ``dairy`` category, creating it if the test has not seeded it.

    Tests may combine this fixture with ``seed_categories`` (which already inserts
    ``dairy``), so it must be idempotent instead of blindly inserting.
    """
    existing = await db_session.get(Category, "dairy")
    if existing is not None:
        return existing

    category = Category(
        id="dairy",
        display_name="Dairy",
        icon="🥛",
        default_shelf_life_days=7,
        meal_contexts=["breakfast"],
        sort_order=1,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


@pytest.fixture
async def sample_product(
    db_session: AsyncSession, sample_category: Category
) -> ProductMaster:
    """Create sample product in database for tests."""
    product = ProductMaster(
        id=uuid4(),
        canonical_name="Test Milk 1L",
        category="dairy",
        storage_type="refrigerator",
        default_shelf_life_days=7,
        unit_type="volume",
        default_unit="dl",
        default_quantity=Decimal("1000"),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.fixture(scope="function")
async def db_engine():
    """Create test database engine using PostgreSQL.

    Uses the same PostgreSQL instance as dev, but creates/drops tables
    per test for isolation. Skips automatically when PostgreSQL is unavailable.
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        await engine.dispose()
        if os.environ.get("KYOKKI_TEST_REQUIRE_DB"):
            # CI provides PostgreSQL; a connection failure there is a real failure,
            # not a reason to silently skip the whole DB-backed suite.
            raise
        pytest.skip("PostgreSQL not available")

    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture(autouse=True)
async def _dispose_app_engine() -> AsyncGenerator[None, None]:
    """Drop the application's pooled DB connections after each test.

    pytest-asyncio runs every test in its own event loop. Endpoints that are not
    behind a ``get_db`` override use the module-level engine in ``app.db.session``;
    its pool would otherwise hand a connection created in a previous test's (now
    closed) loop to the next test, which fails with "event loop is closed" style
    errors. Disposing in the loop that created the connections avoids that.

    The cached broadcast Redis client in ``app.services.broadcast_helpers`` has the
    same lifetime problem, so it is closed here as well.
    """
    yield
    await app_engine.dispose()
    await close_redis_client()


@pytest.fixture
def session_factory(db_session: AsyncSession):
    """A session factory handing out the test session without closing it.

    For code that opens its own sessions (the receipt worker, the Telegram bot).
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield db_session

    return factory


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing broadcasts."""
    from unittest.mock import AsyncMock

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()
    return mock_redis
