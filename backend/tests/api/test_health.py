"""Tests for health check endpoint"""
import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Test suite for /api/health endpoint"""

    async def test_health_check_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint should return 200 OK"""
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_check_returns_ok_status(self, client: AsyncClient) -> None:
        """Health endpoint should return status: ok"""
        response = await client.get("/api/health")
        assert response.json() == {"status": "ok"}

    async def test_root_endpoint_returns_welcome_message(self, client: AsyncClient) -> None:
        """Root endpoint should return welcome message"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Kyokki" in data["message"]
