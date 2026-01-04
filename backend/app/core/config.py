from pydantic_settings import BaseSettings
from pydantic import computed_field

class Settings(BaseSettings):
    # Application
    DEBUG: bool = False

    # Database
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379

    # MinerU OCR Service
    MINERU_BASE_URL: str = "http://192.168.0.136:8000"
    MINERU_TIMEOUT: int | None = None  # No timeout for OCR processing
    MINERU_ENABLE_TABLE: bool = True
    MINERU_ENABLE_FORMULA: bool = False

    # LLM Service (OpenAI-compatible endpoint for Ollama/other providers)
    LLM_BASE_URL: str = "http://192.168.0.247:9003/v1"
    LLM_API_KEY: str = "ollama"  # Default for local Ollama
    LLM_MODEL: str = "qwen2-vl"  # Vision model for receipt analysis fallback
    LLM_TEMPERATURE: float = 0.1

    # Open Food Facts API
    OPENFOODFACTS_API_URL: str = "https://world.openfoodfacts.org/api/v2"

    # Fuzzy matching thresholds
    FUZZY_MATCH_THRESHOLD: int = 80  # Minimum score (0-100) for fuzzy match

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()