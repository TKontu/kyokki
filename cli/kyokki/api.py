"""HTTP to the Kyokki API, and its errors mapped to the CLI's exit codes."""

import sys
from dataclasses import dataclass
from typing import Any

import httpx

OK = 0
ERROR = 1
USAGE = 2
NOT_FOUND = 3
AMBIGUOUS = 4
INSUFFICIENT_STOCK = 5
CONFLICT = 6
AUTH = 7

EXIT_FOR_CODE = {
    "not_found": NOT_FOUND,
    "ambiguous": AMBIGUOUS,
    "insufficient_stock": INSUFFICIENT_STOCK,
    "conflict": CONFLICT,
    "invalid": USAGE,
    "auth": AUTH,
}

TIMEOUT_SECONDS = 15.0


class CliError(Exception):
    """A failure to report: ``detail`` is what --json prints, the exit code what we return."""

    def __init__(self, exit_code: int, detail: Any, status: int | None = None) -> None:
        super().__init__(describe(detail))
        self.exit_code = exit_code
        self.detail = detail
        self.status = status


def describe(detail: Any) -> str:
    """One line for a person: the message, or the 422's field errors."""
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("code") or detail)
    if isinstance(detail, list):
        parts = []
        for error in detail:
            if isinstance(error, dict):
                loc = ".".join(str(p) for p in error.get("loc", []) if p != "body")
                msg = str(error.get("msg", error))
                parts.append(f"{loc}: {msg}" if loc else msg)
            else:
                parts.append(str(error))
        return "; ".join(parts) or "invalid request"
    return str(detail)


def exit_code_for(status: int, detail: Any) -> int:
    if status in (401, 403):
        return AUTH
    if status == 422:
        return USAGE
    if status >= 500:
        return ERROR
    if isinstance(detail, dict):
        return EXIT_FOR_CODE.get(str(detail.get("code")), ERROR)
    return ERROR


def error_from(response: httpx.Response) -> CliError:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("detail"), dict | list):
        detail: Any = body["detail"]
    else:
        text = response.text.strip()[:200] or response.reason_phrase
        if isinstance(body, dict) and isinstance(body.get("detail"), str):
            text = body["detail"]
        detail = {"code": f"http_{response.status_code}", "message": text}
    return CliError(
        exit_code_for(response.status_code, detail), detail, response.status_code
    )


@dataclass
class Answer:
    status: int
    body: Any
    replayed: bool


class Api:
    def __init__(
        self,
        url: str,
        token: str | None,
        *,
        transport: httpx.BaseTransport | None = None,
        verbose: bool = False,
    ) -> None:
        self.url = url.rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": "kyokki-cli"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=self.url,
            headers=headers,
            transport=transport,
            timeout=TIMEOUT_SECONDS,
        )
        self._verbose = verbose

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
        idempotency_key: str | None = None,
    ) -> Answer:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        query = {k: v for k, v in (params or {}).items() if v is not None}
        if self._verbose:
            key = f" (Idempotency-Key {idempotency_key})" if idempotency_key else ""
            print(f"> {method} {self.url}{path}{key}", file=sys.stderr)
        try:
            response = self._client.request(
                method, path, params=query or None, json=body, headers=headers
            )
        except httpx.TransportError as exc:
            reason = type(exc).__name__ if not str(exc) else str(exc)
            raise CliError(
                ERROR,
                {"code": "connection", "message": f"cannot reach {self.url}: {reason}"},
            ) from exc
        if self._verbose:
            print(f"< {response.status_code} {response.reason_phrase}", file=sys.stderr)
        if response.is_error:
            raise error_from(response)
        try:
            parsed = response.json() if response.content else None
        except ValueError:
            parsed = response.text
        replayed = response.headers.get("Idempotent-Replayed", "").lower() == "true"
        return Answer(response.status_code, parsed, replayed)
