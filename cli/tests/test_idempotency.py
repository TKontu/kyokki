"""The derived Idempotency-Key: stable within a minute, per command line."""

from datetime import UTC, datetime

import pytest
from conftest import FakeApi, Runner

from kyokki import idempotency

T0 = datetime(2026, 9, 26, 10, 15, 3, tzinfo=UTC)
T0_LATER = datetime(2026, 9, 26, 10, 15, 58, tzinfo=UTC)
T1 = datetime(2026, 9, 26, 10, 16, 0, tzinfo=UTC)

ARGV = ["stock", "add", "Milk", "1", "l"]


def test_stable_within_a_minute() -> None:
    assert idempotency.derive_key(ARGV, T0) == idempotency.derive_key(ARGV, T0_LATER)


def test_changes_across_minutes() -> None:
    assert idempotency.derive_key(ARGV, T0) != idempotency.derive_key(ARGV, T1)


def test_changes_across_arguments() -> None:
    other = ["stock", "add", "Milk", "2", "l"]
    assert idempotency.derive_key(ARGV, T0) != idempotency.derive_key(other, T0)


def test_is_a_sha256_hex_digest() -> None:
    key = idempotency.derive_key(ARGV, T0)
    assert len(key) == 64
    int(key, 16)


@pytest.mark.parametrize(
    "extra",
    [
        ["--token", "abc"],
        ["--token=abc"],
        ["--url", "http://a:1"],
        ["--url=http://a:1"],
        ["--token", "x", "--url", "http://b"],
    ],
)
def test_ignores_url_and_token(extra: list[str]) -> None:
    assert idempotency.derive_key(ARGV + extra, T0) == idempotency.derive_key(ARGV, T0)
    assert idempotency.derive_key(extra + ARGV, T0) == idempotency.derive_key(ARGV, T0)


def test_naive_times_are_utc() -> None:
    naive = datetime(2026, 9, 26, 10, 15, 30)
    assert idempotency.derive_key(ARGV, naive) == idempotency.derive_key(ARGV, T0)


def test_cli_sends_the_derived_key_for_the_frozen_clock(
    api: FakeApi, run: Runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    api.on("POST", "/api/stock/add", 201, {"item": {}, "product_created": False})
    times = iter([T0, T0_LATER, T1])
    monkeypatch.setattr(idempotency, "utc_now", lambda: next(times))
    run(*ARGV)
    first = api.last.headers["Idempotency-Key"]
    run(*ARGV, "--token", "another")
    second = api.last.headers["Idempotency-Key"]
    run(*ARGV)
    third = api.last.headers["Idempotency-Key"]
    assert first == second == idempotency.derive_key(ARGV, T0)
    assert third != first
