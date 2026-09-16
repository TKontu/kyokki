"""The JSON formatter has to carry structured extras, or measurements are lost.

Before MVP-R4 it whitelisted four fields, so ``extra={"seconds": ...}`` was silently dropped
and nothing in the pipeline could be timed from the logs.
"""

import json
import logging

from app.core.logging import JSONFormatter


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
