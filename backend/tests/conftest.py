"""Shared pytest fixtures for all tests"""
import pytest
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

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


# TODO: Add database fixtures when models are created
# @pytest.fixture
# async def db_session():
#     """Create async database session for testing"""
#     pass
