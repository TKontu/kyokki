"""Settings parsing from environment variables."""

import pytest

from app.core.config import BACKEND_ROOT, ENV_FILES, PROJECT_ROOT, Settings

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
        "MINERU_BASE_URL",
        "MINERU_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = _settings(monkeypatch)
    assert settings.LLM_BASE_URL == "http://192.168.0.94:9292/v1"
    assert settings.LLM_MODEL == "c2.muse-glimmer"
    assert settings.LLM_MAX_TOKENS == 8192
    assert settings.LLM_TIMEOUT == 180.0
    assert settings.LLM_REASONING_STRENGTH == "low"
    assert settings.MINERU_BASE_URL == "http://192.168.0.94:8008"
    assert settings.MINERU_LANG == "latin"
    assert settings.MINERU_TIMEOUT == 120.0


def test_receipt_worker_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("RECEIPT_WORKER_POLL_SECONDS", "RECEIPT_STALE_MINUTES"):
        monkeypatch.delenv(key, raising=False)
    settings = _settings(monkeypatch)
    assert settings.RECEIPT_WORKER_POLL_SECONDS == 2.0
    assert settings.RECEIPT_STALE_MINUTES == 10


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


def test_unknown_env_keys_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """The root .env carries legacy prototype keys (DATABASE_URL, OLLAMA_HOST).

    With the pydantic-settings default of extra="forbid" they aborted every local
    backend process - uvicorn, the worker, alembic, the seeds and pytest alike.
    """
    settings = _settings(
        monkeypatch,
        OLLAMA_HOST="http://192.168.0.94:11434",
        GEMINI_API_KEY="unused-legacy-key",
    )
    assert settings.POSTGRES_DB == "d"


def test_a_rejected_key_never_reaches_the_error_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extra="forbid" printed each rejected key *with its value*, which is how
    three sessions leaked the dev password into a transcript."""
    secret = "postgresql+asyncpg://kyokki_user:PLAINTEXT-PASSWORD@localhost/kyokki"
    settings = _settings(monkeypatch, DATABASE_URL=secret)
    # The computed field wins; the env value is ignored rather than echoed back.
    assert settings.DATABASE_URL == "postgresql+asyncpg://u:p@db/d"


def test_env_file_search_order_prefers_the_backend_copy() -> None:
    """backend/.env is the documented home; the repo-root .env stays supported so
    an existing workstation keeps working."""
    assert ENV_FILES == (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env")
    assert Settings.model_config["env_file"] == ENV_FILES


_HASH = "a" * 64


def test_api_tokens_default_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """No tokens means the API stays open, exactly as before AG1."""
    monkeypatch.delenv("KYOKKI_API_TOKENS", raising=False)
    assert _settings(monkeypatch).KYOKKI_API_TOKENS == []
    assert _settings(monkeypatch, KYOKKI_API_TOKENS="").KYOKKI_API_TOKENS == []


def test_api_tokens_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch,
        KYOKKI_API_TOKENS=f"ipad:write:{_HASH}, hermes:read:{'b' * 64}",
    )
    assert [
        f"ipad:write:{_HASH}",
        f"hermes:read:{'b' * 64}",
    ] == settings.KYOKKI_API_TOKENS


def test_malformed_api_token_fails_at_load_without_the_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.api_tokens import ApiTokenConfigError

    with pytest.raises(ApiTokenConfigError) as exc:
        _settings(monkeypatch, KYOKKI_API_TOKENS=f"hermes:admin:{_HASH}")
    assert "'hermes'" in str(exc.value)
    assert _HASH not in str(exc.value)
