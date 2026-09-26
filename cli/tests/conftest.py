"""A fake Kyokki API over httpx.MockTransport, and a runner for the CLI against it."""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from kyokki import cli, output

URL = "http://kyokki.test:8000"
TOKEN = "s3cr3t-t0ken-VALUE-9f8e7d"
PRODUCT_ID = "0b6f7a3e-8d4c-4a53-9d1e-2f6c1b7e9a01"
ITEM_ID = "5c1e2d3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f"

Handler = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeApi:
    """Answers per (method, path); records every request it sees."""

    routes: dict[tuple[str, str], Handler | httpx.Response] = field(
        default_factory=dict
    )
    requests: list[httpx.Request] = field(default_factory=list)
    down: bool = False

    def on(
        self,
        method: str,
        path: str,
        status: int = 200,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.routes[(method, path)] = httpx.Response(status, json=body, headers=headers)

    def error(self, method: str, path: str, status: int, detail: Any) -> None:
        self.on(method, path, status, {"detail": detail})

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("Connection refused", request=request)
        answer = self.routes.get((request.method, request.url.path))
        if answer is None:
            return httpx.Response(404, json={"detail": "Not Found"})
        if callable(answer):
            return answer(request)
        return answer

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)


@dataclass
class Result:
    code: int
    out: str
    err: str

    def json(self) -> Any:
        return json.loads(self.out)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("KYOKKI_URL", URL)
    monkeypatch.setenv("KYOKKI_TOKEN", TOKEN)
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.delenv("NO_COLOR", raising=False)
    yield


@pytest.fixture
def tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make stdout look like a terminal, for the human-readable output."""
    monkeypatch.setattr(output, "stdout_is_tty", lambda: True)


Runner = Callable[..., Result]


@pytest.fixture
def run(api: FakeApi, capsys: pytest.CaptureFixture[str]) -> Runner:
    def runner(*argv: str) -> Result:
        code = cli.main(list(argv), transport=httpx.MockTransport(api.handle))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return runner
