"""Shared pytest fixtures for all tests."""
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base_class import Base
from app.main import app


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
        transport=ASGITransport(app=app),
        base_url="http://test"
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
            {"name": "Juusto 200g", "price": 3.99, "quantity": 1}
        ],
        "total": 10.06
    }


@pytest.fixture
def sample_product() -> dict:
    """Sample product data for testing"""
    return {
        "name": "Maito",
        "category": "dairy",
        "default_shelf_life_days": 7,
        "opened_shelf_life_days": 3
    }


@pytest.fixture(scope="function")
async def db_engine():
    """Create test database engine using PostgreSQL.

    Uses the same PostgreSQL instance as dev, but creates/drops tables
    per test for isolation.
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        # Ensure cleanup happens even if test fails
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing broadcasts."""
    from unittest.mock import AsyncMock

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()
    return mock_redis
