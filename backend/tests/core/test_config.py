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


def test_llm_defaults_target_the_llama_swap_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_REASONING_STRENGTH",
        "MINERU_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = _settings(monkeypatch)
    assert settings.LLM_BASE_URL == "http://192.168.0.94:9292/v1"
    assert settings.LLM_MODEL == "muse-glimmer"
    assert settings.LLM_MAX_TOKENS == 8192
    assert settings.LLM_TIMEOUT == 180.0
    assert settings.LLM_REASONING_STRENGTH == "low"
    assert settings.MINERU_LANG == "latin"
    assert settings.MINERU_TIMEOUT == 120.0


def test_empty_mineru_timeout_uses_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The example env files ship `MINERU_TIMEOUT=` with no value."""
    assert _settings(monkeypatch, MINERU_TIMEOUT="").MINERU_TIMEOUT == 120.0


def test_reasoning_strength_accepts_only_documented_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _settings(monkeypatch, LLM_REASONING_STRENGTH="medium").LLM_REASONING_STRENGTH
        == "medium"
    )
    with pytest.raises(ValueError):
        _settings(monkeypatch, LLM_REASONING_STRENGTH="minimal")


def test_reasoning_strength_can_be_disabled_for_other_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _settings(monkeypatch, LLM_REASONING_STRENGTH="").LLM_REASONING_STRENGTH is None
    )


def test_telegram_allowed_chat_ids_comma_separated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch, TELEGRAM_ALLOWED_CHAT_IDS="12345, -1009876")
    assert settings.TELEGRAM_ALLOWED_CHAT_IDS == [12345, -1009876]


def test_telegram_defaults_disable_the_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"):
        monkeypatch.delenv(key, raising=False)
    settings = _settings(monkeypatch)
    assert settings.TELEGRAM_BOT_TOKEN is None
    assert settings.TELEGRAM_ALLOWED_CHAT_IDS == []
    assert settings.TELEGRAM_API_BASE == "https://api.telegram.org"


def test_telegram_token_is_never_rendered(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "123456:SECRET-token-value"
    settings = _settings(monkeypatch, TELEGRAM_BOT_TOKEN=token)
    assert settings.TELEGRAM_BOT_TOKEN is not None
    assert settings.TELEGRAM_BOT_TOKEN.get_secret_value() == token
    assert token not in repr(settings)
    assert token not in str(settings.model_dump())
