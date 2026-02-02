"""Test script to verify external service connections."""
import asyncio

import httpx

from app.core.config import settings
from app.db.session import engine


async def test_database():
    """Test PostgreSQL connection"""
    print("\n=== Testing Database Connection ===")
    try:
        async with engine.connect() as conn:
            result = await conn.execute("SELECT version();")
            row = result.fetchone()
            print(f"✅ Database connected: {row[0][:50]}...")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def test_mineru():
    """Test MinerU OCR endpoint"""
    print("\n=== Testing MinerU OCR Endpoint ===")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.MINERU_BASE_URL}/health")
            if response.status_code == 200:
                print(f"✅ MinerU accessible: {settings.MINERU_BASE_URL}")
                return True
            else:
                print(f"⚠️  MinerU responded with status {response.status_code}")
                return False
    except httpx.ConnectError:
        print(f"❌ MinerU not accessible at {settings.MINERU_BASE_URL}")
        return False
    except Exception as e:
        print(f"❌ MinerU test failed: {e}")
        return False


async def test_ollama():
    """Test Ollama LLM endpoint"""
    print("\n=== Testing Ollama LLM Endpoint ===")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try OpenAI-compatible health endpoint
            response = await client.get(f"{settings.LLM_BASE_URL}/models")
            if response.status_code == 200:
                print(f"✅ Ollama accessible: {settings.LLM_BASE_URL}")
                models = response.json()
                print(f"   Available models: {len(models.get('data', []))} models")
                return True
            else:
                print(f"⚠️  Ollama responded with status {response.status_code}")
                return False
    except httpx.ConnectError:
        print(f"❌ Ollama not accessible at {settings.LLM_BASE_URL}")
        return False
    except Exception as e:
        print(f"❌ Ollama test failed: {e}")
        return False


async def main():
    """Run all connection tests"""
    print("="* 50)
    print(" Kyokki Infrastructure Connection Tests")
    print("="* 50)

    results = {}
    results['database'] = await test_database()
    results['mineru'] = await test_mineru()
    results['ollama'] = await test_ollama()

    print("\n" + "="* 50)
    print(" Summary")
    print("="* 50)
    for service, status in results.items():
        symbol = "✅" if status else "❌"
        print(f"{symbol} {service.capitalize()}: {'Connected' if status else 'Failed'}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All services connected successfully!")
    else:
        print("\n⚠️  Some services are not accessible")

    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
