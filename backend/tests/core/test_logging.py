"""Logging must carry structured extras, and no ``token=`` secret in a message or its args.

Before MVP-R4 it whitelisted four fields, so ``extra={"seconds": ...}`` was silently dropped
and nothing in the pipeline could be timed from the logs. Since AG1 the WebSocket accepts
``?token=<secret>``, and uvicorn logs the query string with every handshake.
"""

import io
import json
import logging
import logging.config

import pytest
from uvicorn.config import LOGGING_CONFIG

from app.core.logging import JSONFormatter, TokenRedactingFilter, setup_logging


def _record(message: str = "Receipt read", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.services.receipt_processing",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJSONFormatter:
    def test_emits_arbitrary_extras(self) -> None:
        entry = json.loads(
            JSONFormatter().format(
                _record(
                    receipt_id="r-1", ocr_seconds=12.3, llm_seconds=57.0, method="text"
                )
            )
        )

        assert entry["receipt_id"] == "r-1"
        assert entry["ocr_seconds"] == 12.3
        assert entry["llm_seconds"] == 57.0
        assert entry["method"] == "text"

    def test_keeps_the_message_and_the_standard_fields(self) -> None:
        entry = json.loads(JSONFormatter().format(_record()))

        assert entry["message"] == "Receipt read"
        assert entry["level"] == "INFO"
        assert entry["logger"] == "app.services.receipt_processing"

    def test_does_not_leak_the_records_own_machinery(self) -> None:
        """Only the caller's extras are added, not every LogRecord attribute."""
        entry = json.loads(JSONFormatter().format(_record()))

        for internal in (
            "msg",
            "args",
            "levelno",
            "pathname",
            "created",
            "relativeCreated",
        ):
            assert internal not in entry

    def test_duration_is_still_reported_in_milliseconds(self) -> None:
        """``log_performance`` emits ``duration``; its published name stays ``duration_ms``."""
        entry = json.loads(JSONFormatter().format(_record(duration=42.5)))

        assert entry["duration_ms"] == 42.5
        assert "duration" not in entry

    def test_a_value_json_cannot_encode_does_not_kill_the_log_line(self) -> None:
        entry = json.loads(JSONFormatter().format(_record(receipt=object())))

        assert isinstance(entry["receipt"], str)


# --- The WebSocket ``?token=`` must not reach a log line through the message or its args.
# Extras (``extra=``) and tracebacks are not scanned; nothing logs a token that way. ---


SECRET = "s3cr3t-Value_123"


def _uvicorn_record(
    msg: str, *args: object, name: str = "uvicorn.error"
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def _filtered(record: logging.LogRecord) -> str:
    assert TokenRedactingFilter().filter(record) is True
    return record.getMessage()


class TestTokenRedactingFilter:
    def test_websocket_accepted_line_loses_the_token(self) -> None:
        line = _filtered(
            _uvicorn_record(
                '%s - "WebSocket %s" [accepted]',
                "10.0.0.5:5123",
                f"/api/ws?token={SECRET}",
            )
        )

        assert SECRET not in line
        assert line == '10.0.0.5:5123 - "WebSocket /api/ws?token=***" [accepted]'

    def test_websocket_403_line_loses_the_token(self) -> None:
        line = _filtered(
            _uvicorn_record(
                '%s - "WebSocket %s" 403', "10.0.0.5:5123", f"/api/ws?token={SECRET}"
            )
        )

        assert line == '10.0.0.5:5123 - "WebSocket /api/ws?token=***" 403'

    def test_a_record_without_a_token_is_unchanged(self) -> None:
        record = _uvicorn_record(
            '%s - "WebSocket %s" [accepted]', "10.0.0.5:5123", "/api/ws"
        )

        line = _filtered(record)

        assert line == '10.0.0.5:5123 - "WebSocket /api/ws" [accepted]'
        assert record.args == ("10.0.0.5:5123", "/api/ws")

    def test_token_between_other_parameters_is_redacted(self) -> None:
        line = _filtered(
            _uvicorn_record(
                '%s - "WebSocket %s" [accepted]',
                "10.0.0.5:5123",
                f"/api/ws?a=1&TOKEN={SECRET}&b=2",
            )
        )

        assert SECRET not in line
        assert "/api/ws?a=1&TOKEN=***&b=2" in line

    def test_http_access_line_is_handled_the_same_way(self) -> None:
        line = _filtered(
            _uvicorn_record(
                '%s - "%s %s HTTP/%s" %d',
                "10.0.0.5:5123",
                "GET",
                f"/api/inventory?token={SECRET}",
                "1.1",
                200,
                name="uvicorn.access",
            )
        )

        assert line == '10.0.0.5:5123 - "GET /api/inventory?token=*** HTTP/1.1" 200'

    def test_token_in_the_message_itself_is_redacted(self) -> None:
        line = _filtered(
            _uvicorn_record(f'"WebSocket /api/ws?token={SECRET}" rejected')
        )

        assert line == '"WebSocket /api/ws?token=***" rejected'

    def test_value_stops_at_whitespace(self) -> None:
        line = _filtered(_uvicorn_record(f"GET /x?token={SECRET} done"))

        assert line == "GET /x?token=*** done"

    def test_a_parameter_merely_ending_in_token_is_left_alone(self) -> None:
        line = _filtered(_uvicorn_record("/x?csrftoken=abc"))

        assert line == "/x?csrftoken=abc"

    def test_token_placeholder_in_the_template_is_formatted_then_redacted(self) -> None:
        # Redacting "?token=%s" alone leaves an argument with no placeholder: formatting
        # fails and logging's error handler prints the raw arguments, secret included.
        line = _filtered(_uvicorn_record("GET %s?token=%s", "/api/ws", SECRET))

        assert SECRET not in line
        assert line == "GET /api/ws?token=***"

    def test_percent_encoded_parameter_name_is_redacted(self) -> None:
        # Starlette decodes the name, so "tok%65n" authenticates exactly like "token".
        line = _filtered(_uvicorn_record("%s", f"/api/ws?tok%65n={SECRET}"))

        assert SECRET not in line
        assert line == "/api/ws?tok%65n=***"


@pytest.fixture
def restore_logging():
    names = ["", "app", "uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy"]
    saved = {
        n: (lg.handlers[:], lg.level, lg.propagate, lg.disabled)
        for n in names
        for lg in [logging.getLogger(n)]
    }
    yield
    for n, (handlers, level, propagate, disabled) in saved.items():
        lg = logging.getLogger(n)
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


def _handlers_reached_from(logger: logging.Logger) -> list[logging.Handler]:
    """The handlers ``Logger.callHandlers`` would use, following propagation."""
    handlers: list[logging.Handler] = []
    current: logging.Logger | None = logger
    while current is not None:
        handlers.extend(current.handlers)
        current = current.parent if current.propagate else None
    return handlers


class TestSetupLoggingRedacts:
    """uvicorn configures its loggers before the app's lifespan calls ``setup_logging``."""

    def test_every_handler_a_uvicorn_or_app_record_reaches_redacts(
        self, restore_logging
    ) -> None:
        logging.config.dictConfig(LOGGING_CONFIG)  # what uvicorn does at start-up
        setup_logging()

        for name in ("app.api.auth", "uvicorn", "uvicorn.error", "uvicorn.access"):
            handlers = _handlers_reached_from(logging.getLogger(name))
            assert handlers, name
            for handler in handlers:
                assert any(
                    isinstance(f, TokenRedactingFilter) for f in handler.filters
                ), (name, handler)

    def test_uvicorn_lines_come_out_redacted(self, restore_logging) -> None:
        logging.config.dictConfig(LOGGING_CONFIG)
        setup_logging()
        stream = io.StringIO()
        for name in ("uvicorn", "uvicorn.access"):
            for handler in logging.getLogger(name).handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(
                    handler, logging.FileHandler
                ):
                    handler.setStream(stream)

        logging.getLogger("uvicorn.error").info(
            '%s - "WebSocket %s" [accepted]', "1.2.3.4:5", f"/api/ws?token={SECRET}"
        )
        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "1.2.3.4:5",
            "GET",
            f"/api/x?token={SECRET}",
            "1.1",
            200,
        )

        output = stream.getvalue()
        assert "token=***" in output
        assert output.count("token=***") == 2
        assert SECRET not in output
