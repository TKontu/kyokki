"""Integration tests for external service connections."""
import httpx
import pytest
from sqlalchemy import text

from app.core.config import settings


@pytest.mark.integration
@pytest.mark.requires_db
class TestDatabaseConnection:
    """Test PostgreSQL database connectivity"""

    async def test_database_is_accessible(self, db_engine) -> None:
        """Database should be accessible and respond to queries"""
        async with db_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1;"))
            row = result.fetchone()
            assert row[0] == 1

    async def test_database_version(self, db_engine) -> None:
        """Database should return version information"""
        async with db_engine.connect() as conn:
            result = await conn.execute(text("SELECT version();"))
            row = result.fetchone()
            assert "PostgreSQL" in row[0]


@pytest.mark.integration
@pytest.mark.requires_mineru
@pytest.mark.slow
class TestMinerUConnection:
    """Test MinerU OCR service connectivity"""

    async def test_mineru_is_accessible(self) -> None:
        """MinerU service should be accessible"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Use the correct health check endpoint
            response = await client.get(f"{settings.MINERU_BASE_URL}/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "healthy"


@pytest.mark.integration
@pytest.mark.requires_ollama
class TestOllamaConnection:
    """Test Ollama LLM service connectivity"""

    async def test_ollama_is_accessible(self) -> None:
        """Ollama service should be accessible"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.LLM_BASE_URL}/models")
            assert response.status_code == 200

    async def test_ollama_has_models(self) -> None:
        """Ollama should have models available"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.LLM_BASE_URL}/models")
            data = response.json()
            assert "data" in data
            assert len(data["data"]) > 0

    async def test_ollama_has_qwen2vl_model(self) -> None:
        """Ollama should have qwen2-vl model configured"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.LLM_BASE_URL}/models")
            data = response.json()
            model_ids = [m["id"] for m in data.get("data", [])]
            # Check if any model contains 'qwen' or matches our configured model
            has_qwen = any("qwen" in mid.lower() for mid in model_ids)
            assert has_qwen, f"qwen2-vl model not found. Available: {model_ids}"
