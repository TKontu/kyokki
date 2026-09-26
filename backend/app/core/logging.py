import json
import logging
import logging.config
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import settings

# Everything the logging module itself puts on a record. Anything else came from a
# caller's ``extra=`` and is worth publishing: MVP-R4 reads per-receipt timings this way.
_RESERVED_FIELDS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__
) | {"asctime", "message", "taskName"}


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Publish whatever the caller passed in ``extra=``; ``log_performance`` measures in
        # milliseconds and keeps its published name.
        for key, value in record.__dict__.items():
            if key in _RESERVED_FIELDS or key.startswith("_"):
                continue
            if key == "duration":
                log_entry["duration_ms"] = value
            else:
                log_entry[key] = value

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        # default=str: an unserialisable extra must not lose the whole line
        return json.dumps(log_entry, ensure_ascii=False, default=str)


# A ``token=`` query parameter carries an API secret: the WebSocket takes ``?token=`` because
# browsers cannot set its headers, and uvicorn logs every handshake and request with the full
# query string. The name must follow ``?`` or ``&``; the value ends at ``&``, whitespace or ``"``.
# Each letter may be percent-encoded ("tok%65n"): Starlette decodes the name, so that spelling
# authenticates too.
_TOKEN_PARAM = re.compile(
    r'([?&](?:t|%74)(?:o|%6f)(?:k|%6b)(?:e|%65)(?:n|%6e)=)[^&\s"]*', re.IGNORECASE
)


def _redact(value: object) -> object:
    return _TOKEN_PARAM.sub(r"\1***", value) if isinstance(value, str) else value


class TokenRedactingFilter(logging.Filter):
    """Rewrite ``token=<value>`` to ``token=***`` in a record's message and string args.

    uvicorn passes the request path as an arg, so the message alone is not enough. The
    filter only rewrites; it never drops a record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.args
            and isinstance(record.msg, str)
            and _TOKEN_PARAM.search(record.msg)
        ):
            # The token sits in the template ("?token=%s"). Redacting the template alone
            # leaves an argument with no placeholder, formatting fails, and logging's error
            # handler prints the raw arguments - the secret - to stderr. Format first.
            try:
                message = record.getMessage()
            except (TypeError, ValueError, KeyError):
                # A template that cannot be formatted anyway: keep it, drop the arguments.
                message = record.msg
            record.msg = _redact(message)
            record.args = None
            return True
        record.msg = _redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact(arg) for key, arg in record.args.items()}
        return True


# uvicorn may install its own handlers on these (its default log config, or a server started
# without ``setup_logging``); any handler found on them gets the filter too. After
# ``setup_logging`` the ``uvicorn`` logger's handlers are the console and file ones above.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def setup_logging() -> None:
    """Setup structured logging configuration"""

    # Get project root and create logs directory
    # Check if running in Docker (path /app exists) or locally
    if Path("/app").exists():
        log_dir = Path("/app/logs")
    else:
        # Local development: use project root / logs
        project_root = Path(__file__).parent.parent.parent.parent
        log_dir = project_root / "logs"

    log_dir.mkdir(exist_ok=True, parents=True)

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"redact_tokens": {"()": TokenRedactingFilter}},
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
            "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "standard" if settings.DEBUG else "json",
                "stream": sys.stdout,
                "filters": ["redact_tokens"],
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filename": str(log_dir / "app.log"),
                "filters": ["redact_tokens"],
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "json",
                "filename": str(log_dir / "error.log"),
                "filters": ["redact_tokens"],
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
            },
        },
        "loggers": {
            "app": {
                "level": "DEBUG" if settings.DEBUG else "INFO",
                "handlers": ["console", "file", "error_file"],
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "sqlalchemy": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["console", "file"],
        },
    }

    logging.config.dictConfig(logging_config)

    # Handler-level, so records propagated from child loggers are covered as well.
    for name in _UVICORN_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, TokenRedactingFilter) for f in handler.filters):
                handler.addFilter(TokenRedactingFilter())


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name"""
    return logging.getLogger(f"app.{name}")


class LoggerMixin:
    """Mixin class to add logging capabilities to any class"""

    @property
    def logger(self) -> logging.Logger:
        return get_logger(self.__class__.__name__)


# Performance logging decorator
def log_performance(operation: str):
    """Decorator to log operation performance"""

    def decorator(func):
        import asyncio
        import functools
        import time

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger("performance")
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                logger.info(
                    "Operation completed successfully",
                    extra={
                        "operation": operation,
                        "duration": duration,
                        "status": "success",
                    },
                )
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"Operation failed: {str(e)}",
                    extra={
                        "operation": operation,
                        "duration": duration,
                        "status": "error",
                        "error": str(e),
                    },
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger("performance")
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                logger.info(
                    "Operation completed successfully",
                    extra={
                        "operation": operation,
                        "duration": duration,
                        "status": "success",
                    },
                )
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                logger.error(
                    f"Operation failed: {str(e)}",
                    extra={
                        "operation": operation,
                        "duration": duration,
                        "status": "error",
                        "error": str(e),
                    },
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
