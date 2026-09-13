"""Settings parsing from environment variables."""

import pytest

from app.core.config import Settings

REQUIRED = {
    "POSTGRES_SERVER": "db",
    "POSTGRES_USER": "u",
    "POSTGRES_PASSWORD": "p",
    "POSTGRES_DB": "d",
    "REDIS_HOST": "redis",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in {**REQUIRED, **env}.items():
        monkeypatch.setenv(key, value)
    # _env_file=None: ignore any local .env so the test only sees the env vars above.
    return Settings(_env_file=None)


def test_allowed_origins_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production stack.env uses a comma-separated string (regression: the API
    container failed to start with 'error parsing value for field ALLOWED_ORIGINS')."""
    settings = _settings(
        monkeypatch, ALLOWED_ORIGINS="http://localhost:3000, http://192.168.0.10:17301"
    )
    assert settings.ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://192.168.0.10:17301",
    ]


def test_allowed_origins_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    settings = _settings(monkeypatch)
    assert settings.ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_database_url_built_from_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    assert settings.DATABASE_URL == "postgresql+asyncpg://u:p@db/d"
