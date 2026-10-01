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
    assert settings.LLM_TIMEOUT == 420.0
    assert settings.LLM_REASONING_STRENGTH == "low"
    assert settings.MINERU_BASE_URL == "http://192.168.0.94:8008"
    assert settings.MINERU_LANG == "latin"
    assert settings.MINERU_TIMEOUT == 120.0


def test_receipt_worker_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "RECEIPT_WORKER_POLL_SECONDS",
        "RECEIPT_STALE_MINUTES",
        "LLM_TIMEOUT",
        "LLM_ESTIMATE_TIMEOUT",
        "MINERU_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = _settings(monkeypatch)
    assert settings.RECEIPT_WORKER_POLL_SECONDS == 2.0
    # Unset, the stale window follows the per-receipt budget (PR #131 F11): OCR 120 s,
    # then max(3 x 420 s, 2 x 420 s + 180 s) = 1380 s -> ceil(23) + 5
    assert settings.RECEIPT_STALE_MINUTES is None
    assert settings.receipt_stale_minutes == 28


@pytest.mark.parametrize("value", ["", "10"])
def test_the_stale_window_never_falls_below_the_model_budget(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Q27 verdict #1: three 420 s model calls fit in 21 minutes, and a 10-minute window
    failed a slow but healthy receipt. An old stack.env still says 10."""
    settings = _settings(
        monkeypatch,
        RECEIPT_STALE_MINUTES=value,
        LLM_TIMEOUT="420",
        LLM_ESTIMATE_TIMEOUT="180",
        MINERU_TIMEOUT="120",
    )
    assert settings.receipt_stale_minutes == 28
    assert settings.receipt_stale_minutes * 60 > 3 * settings.LLM_TIMEOUT + 120


def test_a_longer_stale_window_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, RECEIPT_STALE_MINUTES="45", LLM_TIMEOUT="420")
    assert settings.receipt_stale_minutes == 45


def test_the_stale_window_follows_a_shorter_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        monkeypatch,
        RECEIPT_STALE_MINUTES="",
        LLM_TIMEOUT="60",
        LLM_ESTIMATE_TIMEOUT="60",
        MINERU_TIMEOUT="60",
    )
    # 60 s OCR + 3 x 60 s = 240 s -> 4 + 5
    assert settings.receipt_stale_minutes == 9


def test_a_long_selection_timeout_widens_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #131 F11: product selection runs inside receipt processing with
    LLM_ESTIMATE_TIMEOUT. With 180 s reads and a 600 s selection the worst case is
    120 s OCR + 2 x 180 s + 600 s = 18 minutes; the old 3 x LLM_TIMEOUT gave 14."""
    settings = _settings(
        monkeypatch,
        RECEIPT_STALE_MINUTES="",
        LLM_TIMEOUT="180",
        LLM_ESTIMATE_TIMEOUT="600",
        MINERU_TIMEOUT="120",
    )
    assert settings.receipt_stale_minutes == 23


def test_estimates_and_selection_have_their_own_shorter_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Q27 verdict #17: the synchronous "Re-estimate all" must not wait 7 minutes a batch.

    The default rose from 180 to 300 (2026-09-30): the llama-swap gateway notice says a
    cold start now takes 2 to 5 minutes."""
    monkeypatch.delenv("LLM_ESTIMATE_TIMEOUT", raising=False)
    settings = _settings(monkeypatch)
    assert settings.LLM_ESTIMATE_TIMEOUT == 300.0
    assert _settings(monkeypatch, LLM_ESTIMATE_TIMEOUT="90").LLM_ESTIMATE_TIMEOUT == 90


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


# --- ComfyUI (Q18-G1) --------------------------------------------------------------------


def test_comfyui_defaults_leave_it_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("COMFYUI_BASE_URL", "COMFYUI_TIMEOUT", "COMFYUI_POLL_INTERVAL"):
        monkeypatch.delenv(key, raising=False)
    settings = _settings(monkeypatch)
    assert settings.COMFYUI_BASE_URL == ""
    assert settings.COMFYUI_TIMEOUT == 300.0
    assert settings.COMFYUI_POLL_INTERVAL == 2.0


def test_comfyui_base_url_never_hardcoded_but_settable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        monkeypatch,
        COMFYUI_BASE_URL="http://192.168.0.94:9292/upstream/a4.comfyui",
    )
    assert settings.COMFYUI_BASE_URL == "http://192.168.0.94:9292/upstream/a4.comfyui"


@pytest.mark.parametrize("value", ["59", "0", "-10"])
def test_comfyui_timeout_below_60_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    with pytest.raises(ValueError):
        _settings(monkeypatch, COMFYUI_TIMEOUT=value)


def test_comfyui_timeout_at_the_floor_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _settings(monkeypatch, COMFYUI_TIMEOUT="60").COMFYUI_TIMEOUT == 60.0


# --- LLM_API_KEY (llama-swap now requires one, 2026-09-30) -------------------------------


def test_llm_api_key_defaults_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert _settings(monkeypatch).LLM_API_KEY == ""


def test_llm_api_key_warns_at_startup_when_empty(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The warning names LLM_API_KEY and never logs its value."""
    import logging

    from app.core.config import _warn_if_llm_api_key_missing

    empty = _settings(monkeypatch, LLM_API_KEY="")
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _warn_if_llm_api_key_missing(empty)
    assert any("LLM_API_KEY" in record.message for record in caplog.records)


def test_llm_api_key_is_silent_when_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    from app.core.config import _warn_if_llm_api_key_missing

    secret = "sk-llama-swap-secret-value"
    present = _settings(monkeypatch, LLM_API_KEY=secret)
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _warn_if_llm_api_key_missing(present)
    assert caplog.records == []
    assert secret not in caplog.text


def test_module_level_call_warns_when_the_module_loads_with_an_empty_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """review verdict #9: the `_warn_if_llm_api_key_missing(settings)` call that actually
    fires at import time (config.py's last line) was untested - only the function body
    was. Reloading the module re-runs that line with the warning as a fresh assertion.

    `importlib.reload` replaces the module's entire namespace, including the `settings`
    singleton every other module imported a reference to - reloading it again afterwards
    with "restore" env vars is not enough, because those restore values are never the
    *real* ones (e.g. the actual CI database name), so other tests that read
    `app.core.config.settings` fresh would see the wrong POSTGRES_DB/LLM_API_KEY for the
    rest of the run. A snapshot-and-restore of the whole module namespace avoids this: it
    puts back the exact pre-test objects, not a reconstruction from guessed values.
    """
    import importlib
    import logging

    import app.core.config as config_module

    original_namespace = dict(vars(config_module))
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LLM_API_KEY", "")
    try:
        with caplog.at_level(logging.WARNING, logger="app.core.config"):
            importlib.reload(config_module)
        assert any("LLM_API_KEY" in record.message for record in caplog.records)
    finally:
        vars(config_module).clear()
        vars(config_module).update(original_namespace)


# --- LLM_ESTIMATE_TIMEOUT (raised from 180 to 300, 2026-09-30) ---------------------------


def test_the_stale_window_budget_still_follows_three_llm_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM_ESTIMATE_TIMEOUT's default rose from 180 to 300 s (the llama-swap gateway notice:
    cold starts now take 2 to 5 minutes), but 3 x LLM_TIMEOUT (1260 s) still dominates
    2 x LLM_TIMEOUT + LLM_ESTIMATE_TIMEOUT (1140 s), so the stale-window budget is unchanged."""
    settings = _settings(
        monkeypatch,
        RECEIPT_STALE_MINUTES="",
        LLM_TIMEOUT="420",
        LLM_ESTIMATE_TIMEOUT="300",
        MINERU_TIMEOUT="120",
    )
    assert 3 * settings.LLM_TIMEOUT == 1260
    assert 2 * settings.LLM_TIMEOUT + settings.LLM_ESTIMATE_TIMEOUT == 1140
    assert settings.receipt_stale_minutes == 28
