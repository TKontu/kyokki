import logging
import logging.config
import json
import sys
from datetime import datetime
from typing import Any, Dict
from pathlib import Path

from .config import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if they exist
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id

        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        if hasattr(record, "operation"):
            log_entry["operation"] = record.operation

        if hasattr(record, "duration"):
            log_entry["duration_ms"] = record.duration

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_entry["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging():
    """Setup structured logging configuration"""

    # Create logs directory if it doesn't exist
    log_dir = Path("/app/logs")
    log_dir.mkdir(exist_ok=True)

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "standard" if settings.DEBUG else "json",
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "INFO",
                "formatter": "json",
                "filename": "/app/logs/app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "json",
                "filename": "/app/logs/error.log",
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
            "celery": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["console", "file"],
        },
    }

    logging.config.dictConfig(logging_config)


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
        import time
        import functools
        import asyncio

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger("performance")
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                logger.info(
                    f"Operation completed successfully",
                    extra={
                        "operation": operation,
                        "duration": duration,
                        "status": "success"
                    }
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
                        "error": str(e)
                    }
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
                    f"Operation completed successfully",
                    extra={
                        "operation": operation,
                        "duration": duration,
                        "status": "success"
                    }
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
                        "error": str(e)
                    }
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator