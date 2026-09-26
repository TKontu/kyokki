"""The token appears in no output: any command, any error, any help page."""

import httpx
import pytest
from conftest import PRODUCT_ID, TOKEN, FakeApi, Runner
from help_pages import HELP_PAGES

COMMANDS = [
    ["doctor"],
    ["stock", "list", "--q", "milk"],
    ["stock", "add", "Milk", "1", "dl", "--category", "dairy"],
    ["stock", "consume", "Milk", "1", "dl"],
    ["stock", "consume", "Milk", "1", "dl", "--dry-run"],
    ["product", "resolve", "milk"],
    ["product", "name", "add", PRODUCT_ID, "maito"],
    ["category", "list"],
]

ANSWERS = [
    ("ok", None),
    ("401", httpx.Response(401, json={"detail": {"code": "auth", "message": "no"}})),
    ("403", httpx.Response(403, json={"detail": {"code": "auth", "message": "ro"}})),
    ("422", httpx.Response(422, json={"detail": [{"msg": "bad"}]})),
    ("500", httpx.Response(500, text="Internal Server Error")),
    ("down", "down"),
]


def ok(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/whoami":
        return httpx.Response(
            200, json={"name": "hermes", "scopes": ["read"], "auth_enabled": True}
        )
    if request.url.path.startswith("/api/stock/"):
        return httpx.Response(200, json={"item": {}, "product_created": False})
    return httpx.Response(200, json=[] if request.method == "GET" else {})


def assert_clean(out: str, err: str) -> None:
    assert TOKEN not in out
    assert TOKEN not in err


@pytest.fixture(params=[False, True], ids=["json", "tty"])
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    from kyokki import output

    monkeypatch.setattr(output, "stdout_is_tty", lambda: request.param)
    return bool(request.param)


@pytest.mark.parametrize("argv", COMMANDS, ids=[" ".join(c[:2]) for c in COMMANDS])
@pytest.mark.parametrize("answer", ANSWERS, ids=[a[0] for a in ANSWERS])
@pytest.mark.parametrize("token_flag", [False, True], ids=["env", "flag"])
def test_no_token_in_output(
    api: FakeApi,
    run: Runner,
    mode: bool,
    argv: list[str],
    answer: tuple[str, object],
    token_flag: bool,
) -> None:
    _, response = answer
    if response == "down":
        api.down = True
    for method in ("GET", "POST"):
        for path in (
            "/api/health/live",
            "/api/whoami",
            "/api/stock",
            "/api/stock/add",
            "/api/stock/consume",
            "/api/products/resolve",
            f"/api/products/{PRODUCT_ID}/names",
            "/api/categories",
        ):
            if isinstance(response, httpx.Response) and path != "/api/health/live":
                api.routes[(method, path)] = response
            else:
                api.routes[(method, path)] = ok
    extra = ["--token", TOKEN] if token_flag else []
    result = run(*extra, *argv, "--verbose")
    assert_clean(result.out, result.err)


@pytest.mark.parametrize("argv", HELP_PAGES.values(), ids=HELP_PAGES.keys())
def test_no_token_in_help(run: Runner, argv: list[str]) -> None:
    result = run("--token", TOKEN, *argv)
    assert result.code == 0
    assert_clean(result.out, result.err)


@pytest.mark.parametrize(
    "argv",
    [
        ["--token", TOKEN, "bogus"],
        ["stock", "add", "--token", TOKEN],
        ["stock", "list", "--location", TOKEN],
        ["product", "name", "add", TOKEN, "x"],
        [f"--token={TOKEN}", "stock", "add", "Milk", TOKEN],
    ],
)
def test_no_token_in_usage_errors(run: Runner, argv: list[str]) -> None:
    result = run(*argv)
    assert result.code == 2
    assert_clean(result.out, result.err)


def test_no_token_in_a_server_error_that_echoes_it(api: FakeApi, run: Runner) -> None:
    api.error(
        "GET", "/api/stock", 401, {"code": "auth", "message": f"Unknown token {TOKEN}"}
    )
    result = run("stock", "list", "--verbose")
    assert result.code == 7
    assert_clean(result.out, result.err)
