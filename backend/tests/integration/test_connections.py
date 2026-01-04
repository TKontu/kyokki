"""Integration tests for external service connections"""
import pytest
import httpx
from app.core.config import settings
from app.db.session import engine


@pytest.mark.integration
@pytest.mark.requires_db
class TestDatabaseConnection:
    """Test PostgreSQL database connectivity"""

    async def test_database_is_accessible(self) -> None:
        """Database should be accessible and respond to queries"""
        async with engine.connect() as conn:
            result = await conn.execute("SELECT 1;")
            row = result.fetchone()
            assert row[0] == 1

    async def test_database_version(self) -> None:
        """Database should return version information"""
        async with engine.connect() as conn:
            result = await conn.execute("SELECT version();")
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
            # Try root endpoint since /health doesn't exist
            response = await client.get(settings.MINERU_BASE_URL)
            # Accept 200 or 404 (service is running)
            assert response.status_code in [200, 404]


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
