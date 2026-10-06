import logging
import math
from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.api_tokens import parse_token_entries

# backend/app/core/config.py -> backend/ -> the repository root
BACKEND_ROOT = Path(__file__).parent.parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent

# Both are read, later wins. backend/.env is where the file belongs (the backend is
# what reads it); the repo-root .env stays supported so an existing workstation and
# the dev compose file keep working unchanged.
ENV_FILES = (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env")


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

    # API access tokens (AG1): comma-separated name:scope:sha256hex entries, scope
    # read|write. Empty leaves /api open, as before. Generate entries with
    # `python -m app.core.api_tokens new NAME SCOPE`; only the hash lives here.
    KYOKKI_API_TOKENS: Annotated[list[str], NoDecode] = []

    @field_validator("KYOKKI_API_TOKENS", mode="before")
    @classmethod
    def split_api_tokens(cls, v: object) -> object:
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return v

    @field_validator("KYOKKI_API_TOKENS", mode="after")
    @classmethod
    def validate_api_tokens(cls, v: list[str]) -> list[str]:
        # Raises ApiTokenConfigError (not ValueError) so the hashes are not echoed.
        parse_token_entries(v)
        return v

    # MinerU OCR Service
    MINERU_BASE_URL: str = (
        "http://192.168.0.94:8008"  # host port 8008 -> container 8000
    )
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
    LLM_API_KEY: str = ""  # the llama-swap key (required since 2026-09-30)
    # The c0.* copies share a GPU reserved for the operator's agent; Kyokki uses c2.*
    LLM_MODEL: str = "c2.muse-glimmer"
    LLM_TEMPERATURE: float = 0.1
    # Reasoning plus a 49-line receipt with generic names took 3758 tokens (MVP-R2 e2e)
    LLM_MAX_TOKENS: int = 8192
    # seconds; receipts are background jobs, and the Q27 line-accounting contract made a
    # 49-line read take up to ~240 s on muse-glimmer (docs/vLLM_MANUAL_TEST.md)
    LLM_TIMEOUT: float = 420.0
    # seconds; the catalog estimate and product selection calls answer a short list, and
    # "Re-estimate all" waits for them synchronously, so they do not get the receipt budget.
    # Raised from 180 (2026-09-30): the llama-swap gateway notice says a cold start now takes
    # 2 to 5 minutes. 3 x LLM_TIMEOUT still dominates the stale-window budget at 1260 s, so
    # this change does not move receipt_stale_minutes.
    LLM_ESTIMATE_TIMEOUT: float = 300.0
    # Sent as chat_template_kwargs.reasoning_strength (Muse Glimmer accepts only these values).
    # Set to an empty value for models whose template has no such argument.
    LLM_REASONING_STRENGTH: Literal["xhigh", "high", "medium", "low"] | None = "low"

    @field_validator("LLM_REASONING_STRENGTH", mode="before")
    @classmethod
    def empty_reasoning_strength_means_none(cls, v: object) -> object:
        return None if v == "" else v

    # ComfyUI (Q18-G1/G2): generates a flat icon for a food product with no exact emoji (the
    # gap). Empty disables the client entirely - the Kyokki server cannot reach the GPU host
    # yet (ComfyUI is loopback-only on 192.168.0.94; a media-gateway is planned but not built).
    # e.g. http://192.168.0.94:9292/upstream/a4.comfyui - never hardcode the host.
    COMFYUI_BASE_URL: str = ""
    # Seconds for one render job overall, including any 503-with-Retry-After waits. Cold start
    # is ~14s; SDXL+LoRA+IP-Adapter+BiRefNet at 25 steps measured ~22.5s, but a busy GPU or a
    # drain can take much longer. Never below 60s. A `pending` older than twice this counts as
    # stale (services/product_icons.py).
    COMFYUI_TIMEOUT: float = 300.0
    COMFYUI_POLL_INTERVAL: float = 2.0
    # Pixels a side the generated icon is stored at (Q18-G2), downscaled with Pillow from
    # ComfyUI's fixed 1024x1024 canvas - sharp on the iPad tile, small to store and serve.
    ICON_IMAGE_SIZE: int = 256

    # Icon curation (operator ruling 2026-10-03): on the operator's own develop build, the
    # cook can mark a good generated icon as canonical, ready to submit to the repo's icon
    # library. False everywhere else - this is a developer workflow, not a cook-facing
    # feature, so it defaults off.
    ICON_CURATION_ENABLED: bool = False

    @field_validator("COMFYUI_TIMEOUT")
    @classmethod
    def comfyui_timeout_has_a_floor(cls, v: float) -> float:
        if v < 60:
            raise ValueError("COMFYUI_TIMEOUT must be at least 60 seconds")
        return v

    # Telegram receipt drop-in bot (MVP-T1). The bot is disabled while no token is set.
    # Receipt queue worker (python -m app.worker, MVP-R3)
    RECEIPT_WORKER_POLL_SECONDS: float = 2.0  # idle wait between queue checks
    # Processing longer than this is treated as failed. Unset or empty, it follows the model
    # budget; a value below the budget is raised to it (see `receipt_stale_minutes`).
    RECEIPT_STALE_MINUTES: int | None = None

    @field_validator("RECEIPT_STALE_MINUTES", mode="before")
    @classmethod
    def empty_stale_minutes_means_derived(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def receipt_stale_minutes(self) -> int:
        """Minutes a receipt may stay `processing` before `fail_stale` fails it.

        The per-receipt budget (PR #131 F11): OCR of an image (MINERU_TIMEOUT), then up to
        three sequential model calls - the first read and one targeted re-read, each allowed
        LLM_TIMEOUT, and the product selection, which runs inside receipt processing and is
        allowed LLM_ESTIMATE_TIMEOUT. The budget takes the larger of 3 x LLM_TIMEOUT and
        2 x LLM_TIMEOUT + LLM_ESTIMATE_TIMEOUT, so it also covers a stack where selection
        still took LLM_TIMEOUT. The catalog estimates run after confirm, outside receipt
        processing, and are not counted. The window is never below the budget plus 5
        minutes of slack for the database, whatever an older stack.env says (verdict #1).
        """
        models = max(
            3 * self.LLM_TIMEOUT, 2 * self.LLM_TIMEOUT + self.LLM_ESTIMATE_TIMEOUT
        )
        budget = math.ceil((self.MINERU_TIMEOUT + models) / 60) + 5
        return max(self.RECEIPT_STALE_MINUTES or 0, budget)

    # Watched folder receipt drop-in (A2, app/services/receipt_folder.py): a phone or
    # computer sync app (Syncthing, a network share, e-receipts saved from mail) drops
    # files into this folder instead of going through the iPad upload API or the Telegram
    # bot. Empty disables the scan entirely, which is the default.
    RECEIPT_WATCH_DIR: str = ""
    RECEIPT_WATCH_POLL_SECONDS: float = 10.0
    # A file must be unchanged in size and mtime for this long before it is taken, so a
    # sync still writing it is never read half-finished.
    RECEIPT_WATCH_SETTLE_SECONDS: float = 5.0

    # E-mail receipt drop-in (A2, app/services/receipt_mail.py): Finnish chains (K-Ruoka,
    # S-kanava, Lidl Plus) send e-receipts by mail, usually a PDF attachment; the cook
    # forwards them (or has them sent) to a dedicated mailbox. Empty host disables the scan
    # entirely, which is the default.
    RECEIPT_MAIL_HOST: str = ""
    RECEIPT_MAIL_PORT: int = 993
    RECEIPT_MAIL_USER: str = ""
    RECEIPT_MAIL_PASSWORD: SecretStr | None = None
    RECEIPT_MAIL_FOLDER: str = "INBOX"
    # Read mail is moved here (created if missing) so it is never read twice.
    RECEIPT_MAIL_PROCESSED_FOLDER: str = "Kyokki/Processed"
    RECEIPT_MAIL_POLL_SECONDS: float = 300.0
    # Comma list of exact addresses or @domains allowed to mail in a receipt. Required (not
    # just recommended) when RECEIPT_MAIL_HOST is set: anyone who knows the mailbox address
    # must not be able to inject receipts, so an empty allowlist on an enabled adapter
    # refuses to start the scan (app.services.receipt_mail.build_mail_poller).
    RECEIPT_MAIL_ALLOWED_SENDERS: Annotated[list[str], NoDecode] = []

    @field_validator("RECEIPT_MAIL_PASSWORD", mode="before")
    @classmethod
    def empty_mail_password_means_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("RECEIPT_MAIL_ALLOWED_SENDERS", mode="before")
    @classmethod
    def parse_mail_allowed_senders(cls, v: object) -> object:
        if isinstance(v, str):
            return [part.strip() for part in v.split(",") if part.strip()]
        return v

    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    # Chats the bot serves; comma-separated ids. Send /start to the bot to learn yours.
    TELEGRAM_ALLOWED_CHAT_IDS: Annotated[list[int], NoDecode] = []
    TELEGRAM_API_BASE: str = "https://api.telegram.org"
    TELEGRAM_POLL_TIMEOUT: int = 50  # getUpdates long-poll seconds
    # Public root of the PWA, e.g. https://kyokki.example.com. When set, the bot's result
    # messages end with a link to the receipt's review page; empty means no link.
    KYOKKI_PUBLIC_URL: str = ""

    @field_validator("TELEGRAM_BOT_TOKEN", mode="before")
    @classmethod
    def empty_token_means_disabled(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("TELEGRAM_ALLOWED_CHAT_IDS", mode="before")
    @classmethod
    def parse_chat_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(part) for part in v.split(",") if part.strip()]
        return v

    # Largest receipt upload accepted, in bytes. Matches the Telegram bot's own
    # limit (app/telegram_bot/client.py), which is Telegram's.
    MAX_RECEIPT_UPLOAD_BYTES: int = 20 * 1024 * 1024

    # Whether the extraction prompt lists catalog names for the model to reuse.
    #
    # H17 measured dropping it on the 49-line fixture, twice: all 49 lines and all 49
    # generic names survive either way, but the categories the model fills in fall from
    # 40 to 30-31, and extraction is no faster. So the block stays on and the setting
    # exists to turn it off - the spec's "keep it behind a setting for one release if
    # it regresses". Numbers in docs/vLLM_MANUAL_TEST.md.
    EXTRACTION_OFFERS_CATALOG: bool = True

    # Open Food Facts API
    OPENFOODFACTS_API_URL: str = "https://world.openfoodfacts.org/api/v2"

    # Fuzzy matching thresholds
    FUZZY_MATCH_THRESHOLD: int = 80  # Minimum score (0-100) for fuzzy match

    # extra="ignore": the repo-root .env still carries legacy prototype keys
    # (DATABASE_URL, OLLAMA_HOST). Forbidding them aborted every local backend
    # process with an error that printed each rejected key *with its value*.
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _warn_if_llm_api_key_missing(instance: Settings) -> None:
    # app.core.logging imports this module, so get_logger would be a circular import; the
    # plain stdlib logger still reaches stderr even before setup_logging() runs. Never logs
    # the key itself, empty or not.
    if not instance.LLM_API_KEY:
        logging.getLogger("app.core.config").warning(
            "LLM_API_KEY is empty; the llama-swap gateway rejects every request with 401 "
            "(required since 2026-09-30)"
        )


settings = Settings()
_warn_if_llm_api_key_missing(settings)
