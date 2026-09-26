"""Printing: one JSON document for machines, short tables for people.

Also the last line of defence for the token: while the CLI runs, stdout and stderr go
through a writer that masks it, so not even an error echoing it back can print it.
"""

import json
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, TextIO

MASK = "***"
# Shorter values are not treated as secrets: masking "ab" would mangle ordinary output.
MIN_SECRET_LENGTH = 8


def stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def wants_json(json_flag: bool) -> bool:
    return json_flag or not stdout_is_tty()


def print_json(document: Any) -> None:
    print(json.dumps(document, indent=2, ensure_ascii=False))


def note(message: str) -> None:
    print(message, file=sys.stderr)


def number(value: Any) -> str:
    """15.0 as 15 and 1.50 as 1.5; anything else as given."""
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    return "" if value is None else str(value)


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [[str(cell) for cell in row] for row in rows]
    widths = [
        max([len(header)] + [len(row[i]) for row in cells])
        for i, header in enumerate(headers)
    ]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in [list(headers), *cells]
    ]
    return "\n".join(line.rstrip() for line in lines)


class RedactingWriter:
    """A text stream that masks the given secrets in everything written to it."""

    def __init__(self, stream: TextIO, secrets: list[str]) -> None:
        self._stream = stream
        self._secrets = sorted(set(secrets), key=len, reverse=True)

    def write(self, text: str) -> int:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


@contextmanager
def redacted(secrets: list[str]) -> Iterator[None]:
    """Mask ``secrets`` on stdout and stderr for the duration."""
    real = [s for s in secrets if s and len(s) >= MIN_SECRET_LENGTH]
    if not real:
        yield
        return
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = RedactingWriter(saved_out, real)
    sys.stderr = RedactingWriter(saved_err, real)
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
