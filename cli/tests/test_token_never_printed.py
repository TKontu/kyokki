"""The token appears in no output: any command, any error, any help page."""

import httpx
import pytest
from conftest import ITEM_ID, PRODUCT_ID, TOKEN, FakeApi, Runner
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
    ["shopping", "list", "--all"],
    ["shopping", "add", "Milk", "1", "l", "--priority", "urgent"],
    ["shopping", "done", ITEM_ID],
    ["shopping", "done", ITEM_ID, "--undo"],
    ["shopping", "remove", ITEM_ID],
    ["shopping", "generate"],
    ["shopping", "generate", "--dry-run"],
    ["shopping", "export"],
    ["shopping", "export", "--format", "markdown"],
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
    if request.url.path == "/api/shopping/export":
        # An export that echoes the token back is still masked.
        return httpx.Response(
            200, text=f"- {TOKEN} 1 pcs\n", headers={"Content-Type": "text/plain"}
        )
    if request.url.path == "/api/shopping/generate":
        empty: list[object] = []
        return httpx.Response(
            200,
            json={
                "added": empty,
                "updated": empty,
                "unchanged": empty,
                "skipped": empty,
                "dry_run": False,
            },
        )
    if request.method == "DELETE":
        return httpx.Response(204)
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
    for method in ("GET", "POST", "DELETE"):
        for path in (
            "/api/health/live",
            "/api/whoami",
            "/api/stock",
            "/api/stock/add",
            "/api/stock/consume",
            "/api/products/resolve",
            f"/api/products/{PRODUCT_ID}/names",
            "/api/categories",
            "/api/shopping/",
            "/api/shopping/generate",
            "/api/shopping/export",
            f"/api/shopping/{ITEM_ID}",
            f"/api/shopping/{ITEM_ID}/purchase",
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
        ["shopping", "done", TOKEN],
        ["shopping", "add", "Milk", "1", "--priority", TOKEN],
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


# --- a token read from a CRLF file, a non-ASCII token, a short token ---------


@pytest.mark.parametrize("suffix", ["\r", "\n", "\r\n", " "])
@pytest.mark.parametrize("token_flag", [False, True], ids=["env", "flag"])
def test_surrounding_whitespace_is_stripped(
    api: FakeApi,
    run: Runner,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    token_flag: bool,
) -> None:
    api.on("GET", "/api/categories", body=[])
    if token_flag:
        result = run("--token", TOKEN + suffix, "category", "list")
    else:
        monkeypatch.setenv("KYOKKI_TOKEN", TOKEN + suffix)
        result = run("category", "list")
    assert result.code == 0
    assert api.last.headers["Authorization"] == f"Bearer {TOKEN}"
    assert_clean(result.out, result.err)


@pytest.mark.parametrize(
    "bad",
    [f"{TOKEN[:6]}\r{TOKEN[6:]}", f"{TOKEN[:6]}\x1b{TOKEN[6:]}", f"{TOKEN}ä", "tökeni"],
    ids=["inner-cr", "esc", "non-ascii-tail", "non-ascii"],
)
@pytest.mark.parametrize("token_flag", [False, True], ids=["env", "flag"])
@pytest.mark.parametrize("json_mode", [False, True], ids=["tty", "json"])
def test_a_token_with_control_or_non_ascii_characters_is_a_usage_error(
    api: FakeApi,
    run: Runner,
    monkeypatch: pytest.MonkeyPatch,
    bad: str,
    token_flag: bool,
    json_mode: bool,
) -> None:
    from kyokki import output

    monkeypatch.setattr(output, "stdout_is_tty", lambda: not json_mode)
    api.on("GET", "/api/categories", body=[])
    if token_flag:
        result = run("--token", bad, "category", "list")
    else:
        monkeypatch.setenv("KYOKKI_TOKEN", bad)
        result = run("category", "list")
    assert result.code == 2
    assert api.requests == []
    assert "token" in result.err
    for text in (result.out, result.err):
        assert bad not in text
        assert repr(bad)[1:-1] not in text
        assert bad.encode("unicode_escape").decode() not in text
        assert TOKEN not in text


def test_a_header_error_never_prints_the_exception_text(
    api: FakeApi, run: Runner
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.LocalProtocolError(f"Illegal header value b'Bearer {TOKEN}\\r'")

    api.routes[("GET", "/api/categories")] = refuse
    result = run("category", "list")
    assert result.code == 1
    assert "Illegal header" not in result.out + result.err
    assert_clean(result.out, result.err)


@pytest.mark.parametrize("short", ["abc1234", "k9"])
def test_a_short_token_is_masked_too(
    api: FakeApi, run: Runner, monkeypatch: pytest.MonkeyPatch, short: str
) -> None:
    monkeypatch.setenv("KYOKKI_TOKEN", short)
    result = run("stock", "list", "--location", short)
    assert result.code == 2
    assert short not in result.out + result.err
