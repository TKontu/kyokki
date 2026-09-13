from pathlib import Path
from typing import Annotated, Literal

from pydantic import ConfigDict, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode

# Get project root directory (two levels up from this file: backend/app/core/config.py -> project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


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

    # CORS — comma-separated list of allowed origins, e.g.
    # ALLOWED_ORIGINS=http://localhost:3000,http://192.168.0.10:17301
    # NoDecode: pydantic-settings would otherwise try to JSON-decode the env value
    # before the validator below can split it, and the app fails to start.
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # MinerU OCR Service
    MINERU_BASE_URL: str = "http://192.168.0.136:8000"
    MINERU_TIMEOUT: float = 120.0  # seconds; the image falls back to vision on timeout
    # PaddleOCR language pack; it has no Finnish code, "latin" covers å/ä/ö
    MINERU_LANG: str = "latin"
    MINERU_ENABLE_TABLE: bool = True
    MINERU_ENABLE_FORMULA: bool = False

    @field_validator("MINERU_TIMEOUT", mode="before")
    @classmethod
    def empty_mineru_timeout_means_default(cls, v: object) -> object:
        # The example env files ship `MINERU_TIMEOUT=` with no value
        return 120.0 if v == "" else v

    # LLM Service (OpenAI-compatible chat completions; llama-swap gateway on the homelab)
    LLM_BASE_URL: str = "http://192.168.0.94:9292/v1"
    LLM_API_KEY: str = (
        "ollama"  # sent as a bearer token; the gateway does not require one
    )
    LLM_MODEL: str = "muse-glimmer"  # always-loaded; validated in MVP-R0
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096  # reasoning plus a ~50-line receipt fits with margin
    LLM_TIMEOUT: float = 180.0  # seconds; extraction takes ~40-55 s on muse-glimmer
    # Sent as chat_template_kwargs.reasoning_strength (Muse Glimmer accepts only these values).
    # Set to an empty value for models whose template has no such argument.
    LLM_REASONING_STRENGTH: Literal["xhigh", "high", "medium", "low"] | None = "low"

    @field_validator("LLM_REASONING_STRENGTH", mode="before")
    @classmethod
    def empty_reasoning_strength_means_none(cls, v: object) -> object:
        return None if v == "" else v

    # Open Food Facts API
    OPENFOODFACTS_API_URL: str = "https://world.openfoodfacts.org/api/v2"

    # Fuzzy matching thresholds
    FUZZY_MATCH_THRESHOLD: int = 80  # Minimum score (0-100) for fuzzy match

    model_config = ConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8")


settings = Settings()
