"""API errors map to stable exit codes, and print the detail."""

from typing import Any

import pytest
from conftest import PRODUCT_ID, FakeApi, Runner

CONSUME = ("stock", "consume", "milk", "2", "dl")

CANDIDATES = [
    {"product_id": PRODUCT_ID, "name": "milk", "score": 0.9, "source": "canonical"},
    {
        "product_id": "11111111-2222-4333-8444-555555555555",
        "name": "milk oat",
        "score": 0.7,
        "source": "cook",
    },
]

CASES: list[tuple[str, int, Any, int]] = [
    ("not_found", 404, {"code": "not_found", "message": "No product"}, 3),
    (
        "ambiguous",
        409,
        {"code": "ambiguous", "message": "Which one?", "candidates": CANDIDATES},
        4,
    ),
    (
        "insufficient_stock",
        409,
        {
            "code": "insufficient_stock",
            "message": "Only 1 dl",
            "available": 1.0,
            "unit": "dl",
        },
        5,
    ),
    ("invalid", 400, {"code": "invalid", "message": "Unit fits no item"}, 2),
    ("conflict", 409, {"code": "conflict", "message": "Key reused"}, 6),
    ("auth-401", 401, {"code": "auth", "message": "Missing token"}, 7),
    ("auth-403", 403, {"code": "auth", "message": "Read-only token"}, 7),
    (
        "validation-422",
        422,
        [{"loc": ["body", "unit"], "msg": "Unknown unit", "type": "value_error"}],
        2,
    ),
    ("unknown-code", 409, {"code": "surprise", "message": "Hmm"}, 1),
    ("server-500", 500, {"code": "boom", "message": "Internal"}, 1),
]


@pytest.mark.parametrize(
    ("status", "detail", "exit_code"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_error_exit_codes_and_json_detail(
    api: FakeApi, run: Runner, status: int, detail: Any, exit_code: int
) -> None:
    api.error("POST", "/api/stock/consume", status, detail)
    result = run(*CONSUME)
    assert result.code == exit_code
    assert result.json() == detail


@pytest.mark.parametrize(
    ("status", "detail", "exit_code"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_error_exit_codes_human(
    api: FakeApi, run: Runner, tty: None, status: int, detail: Any, exit_code: int
) -> None:
    api.error("POST", "/api/stock/consume", status, detail)
    result = run(*CONSUME)
    assert result.code == exit_code
    assert result.err.startswith("error")


def test_ambiguous_prints_candidates_on_stdout_human(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.error(
        "POST",
        "/api/stock/consume",
        409,
        {"code": "ambiguous", "message": "Which one?", "candidates": CANDIDATES},
    )
    result = run(*CONSUME)
    assert result.code == 4
    assert PRODUCT_ID in result.out
    assert "milk oat" in result.out


def test_insufficient_stock_human_says_how_much(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.error(
        "POST",
        "/api/stock/consume",
        409,
        {
            "code": "insufficient_stock",
            "message": "Only 1 dl",
            "available": 1.0,
            "unit": "dl",
        },
    )
    result = run(*CONSUME)
    assert "available: 1 dl" in result.err


def test_non_json_5xx_is_1(api: FakeApi, run: Runner) -> None:
    import httpx

    api.routes[("GET", "/api/stock")] = httpx.Response(502, text="Bad Gateway")
    result = run("stock", "list")
    assert result.code == 1
    assert result.json()["code"] == "http_502"


def test_connection_error_is_1(api: FakeApi, run: Runner) -> None:
    api.down = True
    result = run("stock", "list")
    assert result.code == 1
    assert result.json()["code"] == "connection"
    assert "cannot reach" in result.json()["message"]


def test_connection_error_human(api: FakeApi, run: Runner, tty: None) -> None:
    api.down = True
    result = run("stock", "list")
    assert result.code == 1
    assert "cannot reach http://kyokki.test:8000" in result.err
