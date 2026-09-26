"""The derived Idempotency-Key: the same command line in the same UTC minute, the same key.

A shell retry of a mutation within the minute replays the first answer instead of adding
or consuming twice. ``--url`` and ``--token`` are left out, so pointing the same command
at the server another way (or with a rotated token) is still the same request; so are
the output-only flags ``--json`` and ``--verbose``, so a retry that adds one replays.
"""

import hashlib
import json
from datetime import UTC, datetime

SECRET_OPTIONS = ("--url", "--token")
OUTPUT_FLAGS = ("--json", "--verbose")


def utc_now() -> datetime:
    return datetime.now(UTC)


def without_connection_options(argv: list[str]) -> list[str]:
    """``argv`` less ``--url``/``--token`` (and their values, in either spelling) and
    the output-only flags."""
    kept: list[str] = []
    skip_next = False
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in SECRET_OPTIONS:
            skip_next = True
            continue
        if arg in OUTPUT_FLAGS:
            continue
        if any(arg.startswith(f"{option}=") for option in SECRET_OPTIONS):
            continue
        kept.append(arg)
    return kept


def derive_key(argv: list[str], now: datetime) -> str:
    """SHA-256 hex of the command line and the UTC minute. Naive times count as UTC."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    minute = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")
    material = json.dumps([without_connection_options(argv), minute])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
