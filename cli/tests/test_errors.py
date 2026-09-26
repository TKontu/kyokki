"""API errors map to stable exit codes, and print the detail."""

import shlex
from typing import Any

import httpx
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


# --- a 2xx that is not JSON ---------------------------------------------------

HTML = "<html><body>Please log in</body></html>"


@pytest.mark.parametrize(
    ("method", "path", "argv"),
    [
        ("GET", "/api/health/live", ["doctor"]),
        ("GET", "/api/whoami", ["doctor"]),
        ("GET", "/api/stock", ["stock", "list"]),
        ("POST", "/api/stock/add", ["stock", "add", "Milk", "1", "dl"]),
        ("POST", "/api/stock/consume", list(CONSUME)),
        ("GET", "/api/products/resolve", ["product", "resolve", "milk"]),
        (
            "POST",
            f"/api/products/{PRODUCT_ID}/names",
            ["product", "name", "add", PRODUCT_ID, "maito"],
        ),
        ("GET", "/api/categories", ["category", "list"]),
    ],
)
@pytest.mark.parametrize("json_mode", [True, False], ids=["json", "tty"])
def test_a_success_that_is_not_json_is_bad_response(
    api: FakeApi,
    run: Runner,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    argv: list[str],
    json_mode: bool,
) -> None:
    from kyokki import output

    monkeypatch.setattr(output, "stdout_is_tty", lambda: not json_mode)
    api.on("GET", "/api/health/live", body={"status": "ok"})
    api.on("GET", "/api/whoami", body={"name": "x", "scopes": [], "auth_enabled": 0})
    api.routes[(method, path)] = httpx.Response(
        200, text=HTML, headers={"Content-Type": "text/html"}
    )
    result = run(*argv)
    assert result.code == 1
    assert "Traceback" not in result.err
    assert HTML not in result.out
    if json_mode:
        assert result.json()["code"] == "bad_response"
    else:
        assert result.err.startswith("error")


def test_doctor_whoami_of_the_wrong_shape_is_bad_response(
    api: FakeApi, run: Runner
) -> None:
    api.on("GET", "/api/health/live", body={"status": "ok"})
    api.on("GET", "/api/whoami", body=["not", "an", "object"])
    result = run("doctor")
    assert result.code == 1
    assert result.json()["code"] == "bad_response"


# --- sent, but no answer --------------------------------------------------------


def _times_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize(
    ("path", "argv"),
    [
        ("/api/stock/add", ["stock", "add", "Milk", "1", "dl"]),
        ("/api/stock/consume", list(CONSUME)),
        (
            f"/api/products/{PRODUCT_ID}/names",
            ["product", "name", "add", PRODUCT_ID, "maito"],
        ),
    ],
)
def test_a_read_timeout_on_a_mutation_is_unknown_outcome(
    api: FakeApi, run: Runner, path: str, argv: list[str]
) -> None:
    api.routes[("POST", path)] = _times_out
    result = run(*argv, "--verbose")
    assert result.code == 1
    detail = result.json()
    key = api.last.headers["Idempotency-Key"]
    assert detail["code"] == "unknown_outcome"
    assert "may have been applied" in detail["message"]
    assert detail["idempotency_key"] == key
    assert detail["retry"] == shlex.join(
        ["kyokki", *argv, "--verbose", "--idempotency-key", key]
    )


def test_unknown_outcome_retry_replaces_an_explicit_key_and_drops_the_token(
    api: FakeApi, run: Runner
) -> None:
    api.routes[("POST", "/api/stock/add")] = _times_out
    result = run(
        "--token",
        "other-token-123",
        "stock",
        "add",
        "oat milk",
        "1",
        "--idempotency-key",
        "k-1",
    )
    detail = result.json()
    assert detail["idempotency_key"] == "k-1"
    assert detail["retry"] == "kyokki stock add 'oat milk' 1 --idempotency-key k-1"


def test_unknown_outcome_human_prints_key_and_retry(
    api: FakeApi, run: Runner, tty: None
) -> None:
    api.routes[("POST", "/api/stock/consume")] = _times_out
    result = run(*CONSUME)
    key = api.last.headers["Idempotency-Key"]
    assert result.code == 1
    assert "may have been applied" in result.err
    assert key in result.err
    assert f"--idempotency-key {key}" in result.err


def test_a_connect_error_on_a_mutation_is_connection(api: FakeApi, run: Runner) -> None:
    api.down = True
    result = run(*CONSUME)
    assert result.code == 1
    assert result.json()["code"] == "connection"


def test_a_read_timeout_on_a_read_is_connection(api: FakeApi, run: Runner) -> None:
    api.routes[("GET", "/api/stock")] = _times_out
    result = run("stock", "list")
    assert result.code == 1
    assert result.json()["code"] == "connection"
    assert "no answer" in result.json()["message"]


# --- string details, unknown ids, bad URLs, usage errors in JSON ---------------


@pytest.mark.parametrize(("status", "exit_code"), [(400, 2), (409, 6)])
def test_a_string_detail_maps_like_the_object_form(
    api: FakeApi, run: Runner, status: int, exit_code: int
) -> None:
    api.error("POST", "/api/stock/consume", status, "Duplicate entry")
    result = run(*CONSUME)
    assert result.code == exit_code
    assert result.json() == {"code": f"http_{status}", "message": "Duplicate entry"}


def test_an_unknown_product_id_is_not_found_on_add_as_on_consume(
    api: FakeApi, run: Runner
) -> None:
    message = f"product '{PRODUCT_ID}' not found"
    api.error("POST", "/api/stock/add", 400, {"code": "invalid", "message": message})
    api.error(
        "POST", "/api/stock/consume", 404, {"code": "not_found", "message": message}
    )
    added = run("stock", "add", PRODUCT_ID, "1")
    consumed = run("stock", "consume", PRODUCT_ID, "1", "dl")
    assert added.code == consumed.code == 3
    assert added.json() == {"code": "not_found", "message": message}


def test_an_add_by_name_that_is_invalid_stays_usage(api: FakeApi, run: Runner) -> None:
    detail = {"code": "invalid", "message": "Category required for new product 'x'"}
    api.error("POST", "/api/stock/add", 400, detail)
    result = run("stock", "add", "x", "1")
    assert result.code == 2
    assert result.json() == detail


@pytest.mark.parametrize("url", ["http://h:abc", "http://[::1", "http://"])
def test_a_malformed_url_is_a_usage_error(api: FakeApi, run: Runner, url: str) -> None:
    result = run("--url", url, "stock", "list")
    assert result.code == 2
    assert "Traceback" not in result.err
    assert "URL" in result.err
    assert api.requests == []


@pytest.mark.parametrize(
    "argv",
    [
        ["stock", "list", "--location", "attic"],
        ["stock", "consume", "milk", "2"],
        ["bogus"],
    ],
)
def test_a_usage_error_in_json_mode_prints_a_json_detail(
    api: FakeApi, run: Runner, argv: list[str]
) -> None:
    result = run(*argv)
    assert result.code == 2
    detail = result.json()
    assert detail["code"] == "usage"
    assert detail["message"]
    assert "usage: kyokki" in result.err


def test_a_missing_url_in_json_mode_prints_a_json_detail(
    run: Runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KYOKKI_URL")
    result = run("stock", "list")
    assert result.code == 2
    assert result.json()["code"] == "usage"
    assert "KYOKKI_URL" in result.json()["message"]


def test_a_usage_error_on_a_tty_prints_nothing_on_stdout(
    run: Runner, tty: None
) -> None:
    result = run("stock", "list", "--location", "attic")
    assert result.code == 2
    assert result.out == ""
